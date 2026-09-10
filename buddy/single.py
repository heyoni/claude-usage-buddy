"""중복 실행 방지.

마스코트가 여러 마리 생기지 않도록, 프로세스가 살아 있는 동안
잠금 파일을 붙잡고 있는다. 프로세스가 죽으면 잠금은 자동으로 풀린다.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

LOCK_PATH = Path.home() / ".claude-usage-buddy" / "buddy.lock"

_handle = None  # 프로세스가 끝날 때까지 열어 둔다


def acquire() -> bool:
    """잠금을 얻으면 True. 이미 다른 마스코트가 떠 있으면 False."""
    global _handle
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK_PATH.open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    handle.write(str(os.getpid()))
    handle.flush()
    _handle = handle
    return True


def running_pid() -> int | None:
    """이미 떠 있는 마스코트의 PID."""
    try:
        return int(LOCK_PATH.read_text().strip())
    except (OSError, ValueError):
        return None
