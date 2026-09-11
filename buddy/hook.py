"""Claude Code 를 켤 때 마스코트가 같이 뜨도록 SessionStart 훅을 건다.

~/.claude/settings.json 의 hooks.SessionStart 에 항목을 하나 넣는다.
기존 설정은 건드리지 않고, 이미 들어 있으면 다시 넣지 않는다.
마스코트는 중복 실행이 막혀 있어서 세션마다 실행돼도 한 마리만 뜬다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
MARKER = "claude-usage-buddy"


def _command() -> str:
    # 훅은 PATH 가 다를 수 있어서 절대 경로를 쓴다.
    # 세션을 붙잡지 않도록 바로 뒤로 보내고 출력은 버린다.
    from . import bundle

    exe = bundle.executable()
    return f'nohup "{exe}" >/dev/null 2>&1 &'


def _load() -> dict:
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except FileNotFoundError:
        return {}
    except ValueError as exc:
        raise SystemExit(f"{SETTINGS_PATH} 가 올바른 JSON 이 아닙니다: {exc}")


def _save(data: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _entries(data: dict) -> list:
    return data.setdefault("hooks", {}).setdefault("SessionStart", [])


def is_installed() -> bool:
    for entry in _entries(_load()):
        for hook in entry.get("hooks", []):
            if MARKER in hook.get("command", ""):
                return True
    return False


def install() -> Path:
    data = _load()
    entries = _entries(data)
    for entry in entries:
        for hook in entry.get("hooks", []):
            if MARKER in hook.get("command", ""):
                hook["command"] = _command()   # 경로가 바뀌었을 수 있으니 갱신
                _save(data)
                return SETTINGS_PATH
    entries.append(
        {
            "matcher": "",
            "hooks": [{"type": "command", "command": _command(), "async": True}],
        }
    )
    _save(data)
    return SETTINGS_PATH


def uninstall() -> None:
    data = _load()
    hooks = data.get("hooks", {})
    if "SessionStart" not in hooks:
        return
    kept = []
    for entry in hooks["SessionStart"]:
        entry["hooks"] = [h for h in entry.get("hooks", []) if MARKER not in h.get("command", "")]
        if entry["hooks"]:
            kept.append(entry)
    if kept:
        hooks["SessionStart"] = kept
    else:
        del hooks["SessionStart"]
    if not hooks:
        del data["hooks"]
    _save(data)
