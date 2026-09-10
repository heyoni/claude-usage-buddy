"""~/.claude 트랜스크립트에서 사용량을 증분 색인하고 집계한다.

Claude Code는 요청마다 assistant 메시지 한 줄을 JSONL로 남기고,
그 안에 모델명·토큰 수·타임스탬프가 들어 있다. 서버가 알려주는
"한도 몇 % 남음" 같은 값은 로컬에 없기 때문에, 이 모듈이 계산하는
사용률은 전부 로컬 로그 기반 추정치다.

전체 재파싱은 비싸므로(수백 MB) 파일별 읽은 위치를 기억해 두고
새로 늘어난 바이트만 읽는다.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from . import pricing

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"


@dataclass(slots=True)
class Entry:
    ts: float          # epoch seconds
    model: str
    inp: int
    out: int
    cw5: int           # 5분 캐시 쓰기
    cw1h: int          # 1시간 캐시 쓰기
    cr: int            # 캐시 읽기

    @property
    def tokens(self) -> int:
        return self.inp + self.out + self.cw5 + self.cw1h + self.cr

    @property
    def cost(self) -> float:
        return pricing.cost_usd(self.model, self.inp, self.out, self.cw5, self.cw1h, self.cr)

    def pack(self) -> list:
        return [round(self.ts, 3), self.model, self.inp, self.out, self.cw5, self.cw1h, self.cr]

    @classmethod
    def unpack(cls, row: list) -> "Entry":
        return cls(row[0], row[1], row[2], row[3], row[4], row[5], row[6])


@dataclass
class Block:
    """5시간 사용 블록 (Claude Code의 rate limit 창과 같은 길이)."""

    start: float
    end: float
    entries: list[Entry] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return sum(e.tokens for e in self.entries)

    @property
    def cost(self) -> float:
        return sum(e.cost for e in self.entries)

    @property
    def last_ts(self) -> float:
        return self.entries[-1].ts if self.entries else self.start

    def is_active(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        return self.start <= now < self.end

    def remaining_seconds(self, now: float | None = None) -> float:
        now = now if now is not None else time.time()
        return max(0.0, self.end - now)


def _parse_ts(value: str | None) -> float | None:
    if not value:
        return None
    try:
        # 예: 2026-09-10T01:42:06.968Z
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _extract(line: str) -> tuple[str, Entry] | None:
    """assistant 한 줄에서 (중복 판별 키, Entry)를 뽑는다. 아니면 None."""
    # json.loads 는 비싸다. 사용량이 없는 줄은 문자열 검사로 먼저 걸러낸다.
    if '"usage"' not in line or '"assistant"' not in line:
        return None
    try:
        rec = json.loads(line)
    except (ValueError, TypeError):
        return None
    if rec.get("type") != "assistant":
        return None
    msg = rec.get("message") or {}
    usage = msg.get("usage") or {}
    if not usage:
        return None
    ts = _parse_ts(rec.get("timestamp"))
    if ts is None:
        return None

    creation = usage.get("cache_creation") or {}
    cw5 = int(creation.get("ephemeral_5m_input_tokens") or 0)
    cw1h = int(creation.get("ephemeral_1h_input_tokens") or 0)
    if not creation:
        # 구버전 포맷에는 세부 구분이 없다. 전부 5분 캐시로 본다.
        cw5 = int(usage.get("cache_creation_input_tokens") or 0)

    entry = Entry(
        ts=ts,
        model=pricing.normalize(msg.get("model")),
        inp=int(usage.get("input_tokens") or 0),
        out=int(usage.get("output_tokens") or 0),
        cw5=cw5,
        cw1h=cw1h,
        cr=int(usage.get("cache_read_input_tokens") or 0),
    )
    if entry.tokens == 0:
        return None

    # 세션을 이어받거나(resume) 분기하면 같은 요청이 여러 파일에 복사된다.
    key = f"{msg.get('id') or ''}:{rec.get('requestId') or ''}"
    if key == ":":
        key = f"{rec.get('uuid') or ts}"
    return key, entry


class UsageIndex:
    """증분 스캔 + 로컬 캐시."""

    def __init__(
        self,
        projects_dir: Path = CLAUDE_PROJECTS,
        state_dir: Path | None = None,
        retention_days: int = 30,
    ) -> None:
        self.projects_dir = Path(projects_dir)
        self.state_dir = Path(state_dir or Path.home() / ".claude-usage-buddy")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self._cache_path = self.state_dir / "index.json"
        self._offsets: dict[str, list] = {}   # path -> [inode, size_read]
        self._entries: list[Entry] = []
        self._seen: set[str] = set()
        self._load()

    # ---------- 영속화 ----------

    def _load(self) -> None:
        try:
            data = json.loads(self._cache_path.read_text())
        except (OSError, ValueError):
            return
        self._offsets = data.get("offsets", {})
        self._entries = [Entry.unpack(r) for r in data.get("entries", [])]
        self._seen = set(data.get("seen", []))

    def _save(self) -> None:
        payload = {
            "version": 1,
            "offsets": self._offsets,
            "entries": [e.pack() for e in self._entries],
            "seen": sorted(self._seen),
        }
        tmp = self._cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, separators=(",", ":")))
        tmp.replace(self._cache_path)

    def _prune(self) -> None:
        cutoff = time.time() - self.retention_days * 86400
        kept = [e for e in self._entries if e.ts >= cutoff]
        if len(kept) != len(self._entries):
            self._entries = kept
            # seen 집합이 무한히 커지지 않도록 같이 정리한다. 잘라낸 구간의
            # 요청이 다시 들어올 일은 없다(파일 오프셋도 이미 지나갔다).
            if len(self._seen) > 200_000:
                self._seen = set()

    # ---------- 스캔 ----------

    def refresh(self) -> int:
        """새로 늘어난 부분만 읽는다. 새로 추가된 요청 수를 반환."""
        if not self.projects_dir.is_dir():
            return 0
        cutoff = time.time() - self.retention_days * 86400
        added = 0
        for path in sorted(self.projects_dir.glob("*/*.jsonl")):
            try:
                st = path.stat()
            except OSError:
                continue
            key = str(path)
            prev = self._offsets.get(key)
            # 보관 기간보다 오래 전에 끝난 파일은 처음부터 건너뛴다.
            if prev is None and st.st_mtime < cutoff:
                self._offsets[key] = [st.st_ino, st.st_size]
                continue
            offset = 0
            if prev and prev[0] == st.st_ino and prev[1] <= st.st_size:
                offset = prev[1]
            if offset == st.st_size:
                continue
            added += self._scan_file(path, offset)
            self._offsets[key] = [st.st_ino, st.st_size]

        # 사라진 파일의 오프셋 정리
        for key in [k for k in self._offsets if not Path(k).exists()]:
            del self._offsets[key]

        self._prune()
        self._entries.sort(key=lambda e: e.ts)
        self._save()
        return added

    def _scan_file(self, path: Path, offset: int) -> int:
        added = 0
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(offset)
                for line in fh:
                    got = _extract(line)
                    if got is None:
                        continue
                    key, entry = got
                    if key in self._seen:
                        continue
                    self._seen.add(key)
                    self._entries.append(entry)
                    added += 1
        except OSError:
            return added
        return added

    @property
    def entries(self) -> list[Entry]:
        return self._entries


# ---------- 집계 ----------


def build_blocks(entries: list[Entry], block_hours: int = 5) -> list[Block]:
    """연속된 요청을 5시간 블록으로 묶는다.

    블록은 첫 요청 시각을 정시로 내린 지점에서 시작하고, 블록 길이를
    넘어서거나 요청 간 공백이 블록 길이보다 크면 새 블록이 열린다.
    (ccusage 의 session block 과 같은 규칙)
    """
    span = block_hours * 3600
    blocks: list[Block] = []
    current: Block | None = None
    for entry in entries:
        if current is None or entry.ts >= current.end or entry.ts - current.last_ts >= span:
            start = entry.ts - (entry.ts % 3600)
            current = Block(start=start, end=start + span)
            blocks.append(current)
        current.entries.append(entry)
    return blocks


def _sum(entries: list[Entry]) -> tuple[int, float]:
    return sum(e.tokens for e in entries), sum(e.cost for e in entries)


@dataclass
class Snapshot:
    """말풍선 한 장에 들어갈 모든 수치."""

    generated_at: float
    block: Block | None
    block_tokens: int
    block_cost: float
    block_remaining: float
    limit_cost: float
    percent: float
    today_tokens: int
    today_cost: float
    week_tokens: int
    week_cost: float
    by_model: list[tuple[str, float]]   # (표시명, 비용) 내림차순
    total_requests: int
    idle_seconds: float                 # 마지막 요청 이후 지난 시간
    doze_after: float                   # 이만큼 조용하면 존다

    @property
    def has_data(self) -> bool:
        return self.total_requests > 0

    @property
    def dozing(self) -> bool:
        """블록은 열려 있지만 한동안 조용한 상태."""
        return self.idle_seconds >= self.doze_after

    @property
    def mood(self) -> str:
        """마스코트 표정을 정하는 단계.

        한도를 다 쓴 상태가 가장 먼저다. 그다음이 졸기 — 쓰지 않는 동안에는
        사용률이 얼마든 자게 둔다. 깨어 있을 때만 사용률로 표정을 정한다.
        """
        if self.block is None or not self.block.is_active(self.generated_at):
            return "sleepy"
        if self.percent >= 100:
            return "exhausted"
        if self.dozing:
            return "sleepy"
        if self.percent >= 95:
            return "panic"
        if self.percent >= 80:
            return "worried"
        if self.percent >= 50:
            return "busy"
        return "happy"


def summarize(
    entries: list[Entry],
    block_hours: int = 5,
    manual_limit: float | None = None,
    now: float | None = None,
    doze_after_seconds: float = 1200.0,
) -> Snapshot:
    now = now if now is not None else time.time()
    blocks = build_blocks(entries, block_hours)

    active = blocks[-1] if blocks and blocks[-1].is_active(now) else None
    b_tokens, b_cost = _sum(active.entries) if active else (0, 0.0)

    # 한도 추정: 직접 지정한 값이 없으면 지난 블록들 중 가장 많이 쓴 블록을
    # 기준으로 삼는다. 서버가 주는 실제 한도가 아니라 "내 평소 최대치" 기준.
    past = [b for b in blocks if b is not active]
    if manual_limit and manual_limit > 0:
        limit = manual_limit
    elif past:
        limit = max(b.cost for b in past)
    else:
        limit = 0.0
    limit = max(limit, 0.01)
    percent = min(999.0, b_cost / limit * 100.0)

    midnight = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = midnight.timestamp()
    week_start = (midnight - timedelta(days=6)).timestamp()

    today = [e for e in entries if e.ts >= day_start]
    week = [e for e in entries if e.ts >= week_start]
    t_tokens, t_cost = _sum(today)
    w_tokens, w_cost = _sum(week)

    per_model: dict[str, float] = {}
    for e in today:
        per_model[pricing.display_name(e.model)] = per_model.get(pricing.display_name(e.model), 0.0) + e.cost

    return Snapshot(
        generated_at=now,
        block=active,
        block_tokens=b_tokens,
        block_cost=b_cost,
        block_remaining=active.remaining_seconds(now) if active else 0.0,
        limit_cost=limit,
        percent=percent,
        today_tokens=t_tokens,
        today_cost=t_cost,
        week_tokens=w_tokens,
        week_cost=w_cost,
        by_model=sorted(per_model.items(), key=lambda kv: -kv[1]),
        total_requests=len(entries),
        idle_seconds=(now - entries[-1].ts) if entries else float("inf"),
        doze_after=doze_after_seconds,
    )


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, m = divmod(seconds // 60, 60)
    if h:
        return f"{h}시간 {m}분"
    return f"{m}분"
