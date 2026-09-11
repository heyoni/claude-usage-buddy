"""독립 실행 앱(.app)을 만드는 py2app 설정. packaging/build.sh 가 호출한다."""

import sys
from pathlib import Path

from setuptools import setup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from buddy import __version__  # noqa: E402

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "icon.icns",
    "packages": ["buddy"],
    "includes": ["objc", "AppKit", "Foundation"],
    "excludes": ["tkinter", "test", "unittest", "pydoc_data"],
    "plist": {
        "CFBundleName": "Claude Usage Buddy",
        "CFBundleDisplayName": "Claude Usage Buddy",
        "CFBundleIdentifier": "com.github.claude-usage-buddy",
        "CFBundleVersion": __version__,
        "CFBundleShortVersionString": __version__,
        "LSUIElement": True,               # Dock 에 남기지 않는다 — 마스코트가 곧 UI
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    },
}

setup(
    name="Claude Usage Buddy",
    app=["app_main.py"],
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
