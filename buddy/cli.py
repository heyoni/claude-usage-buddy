"""터미널에서 사용량을 확인하는 명령. GUI 없이도 동작한다."""

from __future__ import annotations

import json

from . import config
from .usage import UsageIndex, fmt_duration, fmt_tokens, summarize


def _snapshot():
    cfg = config.load()
    index = UsageIndex(retention_days=cfg["retention_days"])
    index.refresh()
    return summarize(index.entries, cfg["block_hours"], cfg.get("block_cost_limit"))


def print_report() -> None:
    snap = _snapshot()
    if not snap.has_data:
        print("아직 기록이 없습니다. ~/.claude/projects 를 확인해 주세요.")
        return

    bar_width = 24
    filled = int(bar_width * min(snap.percent, 100) / 100)
    bar = "█" * filled + "░" * (bar_width - filled)

    print("Claude 사용량")
    print("─" * 40)
    if snap.block:
        print(f"5시간 블록   {bar} {snap.percent:.0f}%")
        print(f"             ${snap.block_cost:.2f} · {fmt_tokens(snap.block_tokens)} tok")
        print(f"             {fmt_duration(snap.block_remaining)} 남음 "
              f"(기준 ${snap.limit_cost:.2f})")
    else:
        print("5시간 블록   쉬는 중")
    print("─" * 40)
    print(f"오늘         ${snap.today_cost:.2f} · {fmt_tokens(snap.today_tokens)} tok")
    print(f"최근 7일     ${snap.week_cost:.2f} · {fmt_tokens(snap.week_tokens)} tok")
    if snap.by_model:
        total = sum(cost for _, cost in snap.by_model) or 1.0
        share = ", ".join(f"{n} {c / total * 100:.0f}%" for n, c in snap.by_model[:4])
        print(f"오늘 모델    {share}")
    print()
    print("* 금액은 API 정가 환산 추정치입니다 (구독 실제 청구액 아님)")


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
                "week": {"cost_usd": round(snap.week_cost, 4), "tokens": snap.week_tokens},
                "by_model": [{"model": n, "cost_usd": round(c, 4)} for n, c in snap.by_model],
                "mood": snap.mood,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
