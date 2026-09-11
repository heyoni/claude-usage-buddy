"""지금 독립 실행 앱(.app) 안에서 도는지, 가상환경에서 도는지 구분한다.

py2app 으로 묶인 앱은 sys.executable 이 앱 안의 파이썬을 가리키고,
콘솔 명령 같은 건 없다. 자동 실행이나 훅을 걸 때 실행 파일 경로가 달라진다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_bundled() -> bool:
    return bool(getattr(sys, "frozen", False)) or "RESOURCEPATH" in os.environ


def app_path() -> Path | None:
    """묶인 앱이면 .app 경로."""
    resource = os.environ.get("RESOURCEPATH")
    if not resource:
        return None
    return Path(resource).parent.parent   # Contents/Resources -> Contents -> .app


def executable() -> Path:
    """마스코트를 실행하는 명령의 절대 경로."""
    app = app_path()
    if app is not None:
        macos = app / "Contents" / "MacOS"
        # py2app 은 실행 파일 이름을 앱 이름과 같게 둔다
        for candidate in macos.iterdir():
            if candidate.name != "python" and os.access(candidate, os.X_OK):
                return candidate
    return Path(sys.executable).with_name("claude-usage-buddy")
