"""Claude Code 가 쓰는 계정으로 서버의 실제 사용률을 받아온다.

Claude Code 는 로그인하면 OAuth 토큰을 macOS 키체인에 넣어 두고, /usage 를
치면 그 토큰으로 서버에 물어본다. 여기서도 같은 토큰으로 같은 곳에 물어본다.
그래서 이 값은 추정이 아니라 서버가 실제로 세는 숫자다.

이 주소는 자주 부르면 429 를 돌려준다 (retry-after 약 2분). 그래서
- 응답을 디스크에 캐시해 앱과 CLI 가 같이 쓰고, 60초 안에는 다시 묻지 않는다.
- 429 가 오면 retry-after 만큼 기다리고 그동안은 마지막 값을 그대로 쓴다.
  사용률은 내가 Claude 를 쓸 때만 바뀌므로 몇 분 된 값도 로컬 추정보다 낫다.
- 캐시가 너무 오래됐거나 5시간 창이 이미 지나 버렸으면 None 을 돌려주고
  호출한 쪽이 로컬 추정으로 넘어간다.

공개 문서에 없는 내부 주소라 언제든 바뀔 수 있다. 토큰은 읽기만 하고 갱신은
Claude Code 에 맡긴다 — 만료됐으면 Claude Code 를 한 번 켜면 다시 채워진다.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

KEYCHAIN_SERVICE = "Claude Code-credentials"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CACHE_PATH = Path.home() / ".claude-usage-buddy" / "remote-cache.json"

TIMEOUT = 8.0
MIN_INTERVAL = 60.0          # 이보다 자주는 서버에 묻지 않는다
MAX_AGE = 15 * 60.0          # 이보다 오래된 캐시는 버린다
DEFAULT_BACKOFF = 120.0      # 429 에 retry-after 가 없을 때


@dataclass(frozen=True)
class Window:
    percent: float
    resets_at: float | None     # epoch


@dataclass(frozen=True)
class RemoteUsage:
    fetched_at: float
    five_hour: Window
    seven_day: Window | None

    def is_stale(self, now: float) -> bool:
        if now - self.fetched_at > MAX_AGE:
            return True
        # 5시간 창이 닫혔으면 퍼센트가 0 으로 돌아갔을 텐데 캐시는 모른다
        return bool(self.five_hour.resets_at and self.five_hour.resets_at <= now)


# ---------- 키체인 ----------

def _token() -> str | None:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        oauth = json.loads(result.stdout).get("claudeAiOauth") or {}
    except ValueError:
        return None
    token = oauth.get("accessToken")
    expires = oauth.get("expiresAt")
    if not token:
        return None
    if expires and expires / 1000 <= time.time():
        return None
    return token


# ---------- 파싱 ----------

def _epoch(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _window(block: dict | None) -> Window | None:
    if not isinstance(block, dict):
        return None
    pct = block.get("utilization")
    if pct is None:
        pct = block.get("percent")
    if pct is None:
        return None
    return Window(percent=float(pct), resets_at=_epoch(block.get("resets_at")))


def _parse(body: dict, now: float) -> RemoteUsage | None:
    five = _window(body.get("five_hour"))
    if five is None:
        for limit in body.get("limits") or []:
            if isinstance(limit, dict) and limit.get("kind") == "session":
                five = _window(limit)
                break
    if five is None:
        return None
    return RemoteUsage(fetched_at=now, five_hour=five, seven_day=_window(body.get("seven_day")))


# ---------- 캐시 ----------

def _load_cache() -> tuple[RemoteUsage | None, float]:
    """(마지막 응답, 다음에 물어봐도 되는 시각)"""
    try:
        data = json.loads(CACHE_PATH.read_text())
    except (OSError, ValueError):
        return None, 0.0
    usage = None
    if data.get("usage"):
        u = data["usage"]
        try:
            usage = RemoteUsage(
                fetched_at=u["fetched_at"],
                five_hour=Window(**u["five_hour"]),
                seven_day=Window(**u["seven_day"]) if u.get("seven_day") else None,
            )
        except (KeyError, TypeError):
            usage = None
    return usage, float(data.get("not_before") or 0.0)


def _save_cache(usage: RemoteUsage | None, not_before: float) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps({
            "usage": asdict(usage) if usage else None,
            "not_before": not_before,
        }))
    except OSError:
        pass


# ---------- 공개 함수 ----------

def fetch() -> RemoteUsage | None:
    """서버 사용률. 최근 값이 있으면 그걸 쓰고, 못 구하면 None."""
    now = time.time()
    cached, not_before = _load_cache()
    usable = cached if cached and not cached.is_stale(now) else None

    if now < not_before:
        return usable

    token = _token()
    if not token:
        return usable

    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "claude-usage-buddy",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            try:
                wait = float(exc.headers.get("retry-after") or DEFAULT_BACKOFF)
            except ValueError:
                wait = DEFAULT_BACKOFF
            _save_cache(cached, now + wait)
        else:
            _save_cache(cached, now + MIN_INTERVAL)
        return usable
    except (urllib.error.URLError, ValueError, OSError):
        _save_cache(cached, now + MIN_INTERVAL)
        return usable

    fresh = _parse(body, now)
    if fresh is None:
        _save_cache(cached, now + MIN_INTERVAL)
        return usable
    _save_cache(fresh, now + MIN_INTERVAL)
    return fresh
