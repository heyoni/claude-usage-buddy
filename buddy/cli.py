"""터미널에서 사용량을 확인하는 명령. GUI 없이도 동작한다."""

from __future__ import annotations

import json

from . import config
from .usage import UsageIndex, fmt_duration, fmt_tokens, summarize


def _snapshot():
    from . import remote

    cfg = config.load()
    index = UsageIndex(retention_days=cfg["retention_days"])
    index.refresh()
    minutes = float(cfg.get("doze_after_minutes") or 0)
    server = remote.fetch() if cfg.get("use_server_usage", True) else None
    return summarize(
        index.entries,
        cfg["block_hours"],
        cfg.get("block_cost_limit"),
        doze_after_seconds=minutes * 60.0 if minutes > 0 else float("inf"),
        remote=server,
    )


def print_report() -> None:
    snap = _snapshot()
    if not snap.has_data:
        print("아직 기록이 없습니다. ~/.claude/projects 를 확인해 주세요.")
        return

    bar_width = 24
    filled = int(bar_width * min(snap.percent, 100) / 100)
    bar = "█" * filled + "░" * (bar_width - filled)

    tag = "서버 값" if snap.source == "server" else f"로컬 추정 · 기준 ${snap.limit_cost:.2f}"
    print("Claude 사용량")
    print("─" * 40)
    if snap.block:
        print(f"5시간 블록   {bar} {snap.percent:.0f}%")
        print(f"             ${snap.block_cost:.2f} · {fmt_tokens(snap.block_tokens)} tok")
        import datetime as _dt
        clock = _dt.datetime.fromtimestamp(snap.block_resets_at).strftime("%H:%M") if snap.block_resets_at else "?"
        print(f"             {clock} 초기화 · {fmt_duration(snap.remaining_now())} 남음 ({tag})")
    else:
        print("5시간 블록   쉬는 중")
    if snap.week_percent is not None:
        w_filled = int(bar_width * min(snap.week_percent, 100) / 100)
        w_bar = "█" * w_filled + "░" * (bar_width - w_filled)
        import datetime as _dt
        when = _dt.datetime.fromtimestamp(snap.week_resets).strftime("%m/%d %H:%M") if snap.week_resets else "?"
        print(f"7일 한도     {w_bar} {snap.week_percent:.0f}%")
        print(f"             {when} 초기화")
    print("─" * 40)
    print(f"오늘         ${snap.today_cost:.2f} · {fmt_tokens(snap.today_tokens)} tok")
    print(f"최근 7일     ${snap.week_cost:.2f} · {fmt_tokens(snap.week_tokens)} tok")
    if snap.by_model:
        total = sum(cost for _, cost in snap.by_model) or 1.0
        share = ", ".join(f"{n} {c / total * 100:.0f}%" for n, c in snap.by_model[:4])
        print(f"오늘 모델    {share}")
    print()
    print("* 금액은 API 정가 환산 추정치입니다 (구독 실제 청구액 아님)")


def calibrate(percent: float) -> None:
    """Claude Code 가 알려주는 실제 퍼센트에 눈금을 맞춘다.

    서버가 강제하는 진짜 한도는 로컬에 없어서, 기본값은 "지금까지 가장 많이
    쓴 블록"을 100% 로 본다. 실제 값을 알려 주면 그 지점이 그 퍼센트가 되도록
    기준 금액을 역산해 저장한다.
    """
    if not 0 < percent <= 100:
        print("1 부터 100 사이의 숫자를 넣어 주세요.")
        return

    cfg = config.load()
    index = UsageIndex(retention_days=cfg["retention_days"])
    index.refresh()
    snap = summarize(index.entries, cfg["block_hours"], None)

    if snap.block is None or snap.block_cost <= 0:
        print("지금 열려 있는 블록이 없습니다. Claude Code 를 쓰는 중에 실행해 주세요.")
        return

    limit = snap.block_cost / (percent / 100.0)
    cfg["block_cost_limit"] = round(limit, 2)
    config.save(cfg)

    print(f"현재 블록 환산 비용  ${snap.block_cost:.2f}")
    print(f"이걸 {percent:.0f}% 로 보면  100% = ${limit:.2f}")
    print()
    print(f"기준을 저장했습니다: {config.CONFIG_PATH}")
    print("다음 갱신(최대 1분)부터 마스코트에 반영됩니다.")


def print_json() -> None:
    snap = _snapshot()
    print(
        json.dumps(
            {
                "generated_at": snap.generated_at,
                "block": {
                    "active": snap.block is not None,
                    "cost_usd": round(snap.block_cost, 4),
                    "tokens": snap.block_tokens,
                    "percent": round(snap.percent, 1),
                    "limit_usd": round(snap.limit_cost, 4),
                    "remaining_seconds": int(snap.block_remaining),
                },
                "today": {"cost_usd": round(snap.today_cost, 4), "tokens": snap.today_tokens},
                "by_model": [{"model": n, "cost_usd": round(c, 4)} for n, c in snap.by_model],
                "source": snap.source,
                "week": {"cost_usd": round(snap.week_cost, 4), "tokens": snap.week_tokens,
                         "percent": snap.week_percent, "resets_at": snap.week_resets},
                "idle_seconds": int(snap.idle_seconds) if snap.idle_seconds != float("inf") else None,
                "dozing": snap.dozing,
                "mood": snap.mood,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
