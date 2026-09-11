"""로그인할 때 자동으로 띄우기 위한 LaunchAgent 등록/해제."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.github.claude-usage-buddy"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / ".claude-usage-buddy"


def is_enabled() -> bool:
    return PLIST_PATH.exists()


def _launchctl(*args: str) -> None:
    subprocess.run(["launchctl", *args], check=False, capture_output=True)


def enable() -> Path:
    """현재 실행 중인 파이썬과 프로젝트 위치로 plist를 쓰고 등록한다."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    project_root = str(Path(__file__).resolve().parent.parent)

    # 묶인 앱이면 앱 실행 파일, 설치된 명령이 있으면 그것, 아니면 저장소 모듈
    from . import bundle

    exe = bundle.executable()
    program = [str(exe)] if exe.exists() else [sys.executable, "-m", "buddy"]

    payload = {
        "Label": LABEL,
        "ProgramArguments": program,
        "WorkingDirectory": project_root,
        "EnvironmentVariables": {"PYTHONPATH": project_root},
        "RunAtLoad": True,
        "KeepAlive": False,
        "ProcessType": "Interactive",
        "StandardOutPath": str(LOG_DIR / "buddy.log"),
        "StandardErrorPath": str(LOG_DIR / "buddy.log"),
    }
    with PLIST_PATH.open("wb") as fh:
        plistlib.dump(payload, fh)

    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", f"{domain}/{LABEL}")
    _launchctl("bootstrap", domain, str(PLIST_PATH))
    return PLIST_PATH


def disable() -> None:
    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", f"{domain}/{LABEL}")
    PLIST_PATH.unlink(missing_ok=True)


def toggle() -> bool:
    if is_enabled():
        disable()
        return False
    enable()
    return True
