"""사용자 설정. ~/.claude-usage-buddy/config.json 에 저장된다."""

from __future__ import annotations

import copy
import json
from pathlib import Path

STATE_DIR = Path.home() / ".claude-usage-buddy"
CONFIG_PATH = STATE_DIR / "config.json"

DEFAULTS: dict = {
    # 사용량 다시 읽는 주기(초)
    "refresh_seconds": 60,
    # 사용 블록 길이(시간). Claude Code의 rate limit 창과 같은 5시간이 기본.
    "block_hours": 5,
    # 블록 한도(USD 환산). null 이면 지난 블록 최대치를 기준으로 자동 추정한다.
    "block_cost_limit": None,
    # 트랜스크립트 보관 기간(일). 길수록 첫 색인이 느려진다.
    "retention_days": 30,
    "notify": {
        "enabled": True,
        # 블록 사용률이 이 값을 넘을 때 한 번씩 알린다.
        "thresholds": [50, 80, 95, 100],
        # 새 5시간 블록이 시작되면 알린다.
        "on_block_reset": True,
    },
    "mascot": {
        # 마스코트 크기 배율
        "scale": 1.0,
        # 걷는 속도 배율
        "speed": 1.0,
        # False 면 제자리에 머문다
        "wander": True,
        # 마지막으로 있던 자리 [x, y]. 직접 옮기면 여기에 기록된다.
        "position": None,
        # 말풍선이 저절로 닫히는 시간(초). 0 이면 직접 닫을 때까지 유지.
        # 꾹 누르거나 메뉴로 열면 이 시간과 관계없이 고정된다.
        "bubble_seconds": 3,
    },
}


def _merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load() -> dict:
    try:
        return _merge(DEFAULTS, json.loads(CONFIG_PATH.read_text()))
    except (OSError, ValueError):
        return copy.deepcopy(DEFAULTS)


def save(cfg: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))


def ensure_file() -> Path:
    """설정 파일이 없으면 기본값으로 만들어 준다."""
    if not CONFIG_PATH.exists():
        save(copy.deepcopy(DEFAULTS))
    return CONFIG_PATH
