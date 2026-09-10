"""모델별 단가표와 비용 계산.

가격은 Anthropic 1st-party API의 100만 토큰당 USD 기준이다.
Pro/Max 구독으로 Claude Code를 쓰는 경우 실제로 청구되는 금액은 아니고,
"같은 양을 API로 썼다면 얼마" 를 나타내는 환산값이다.
"""

from __future__ import annotations

# model_id -> (input, output, cache_read) USD / 1M tokens
_PRICES: dict[str, tuple[float, float, float]] = {
    "claude-fable-5-1": (10.00, 50.00, 0.25),
    "claude-mythos-5-1": (10.00, 50.00, 0.25),
    "claude-fable-5": (10.00, 50.00, 1.00),
    "claude-mythos-5": (10.00, 50.00, 1.00),
    "claude-opus-5": (5.00, 25.00, 0.50),
    "claude-opus-4-8": (5.00, 25.00, 0.50),
    "claude-opus-4-7": (5.00, 25.00, 0.50),
    "claude-opus-4-6": (5.00, 25.00, 0.50),
    "claude-opus-4-5": (5.00, 25.00, 0.50),
    "claude-opus-4-1": (15.00, 75.00, 1.50),
    "claude-opus-4": (15.00, 75.00, 1.50),
    "claude-sonnet-5": (2.00, 10.00, 0.20),
    "claude-sonnet-4-6": (3.00, 15.00, 0.30),
    "claude-sonnet-4-5": (3.00, 15.00, 0.30),
    "claude-sonnet-4": (3.00, 15.00, 0.30),
    "claude-haiku-4-5": (1.00, 5.00, 0.10),
    "claude-3-5-haiku": (0.80, 4.00, 0.08),
}

# Claude Code가 모델을 짧은 별칭으로 기록하는 경우가 있다.
_ALIASES = {
    "opus": "claude-opus-5",
    "sonnet": "claude-sonnet-5",
    "haiku": "claude-haiku-4-5",
    "fable": "claude-fable-5-1",
}

# 캐시 쓰기 배수 (input 단가 대비)
CACHE_WRITE_5M = 1.25
CACHE_WRITE_1H = 2.00

# 표에 없는 모델을 만났을 때 쓰는 보수적 기본값 (Opus 등급)
_FALLBACK = _PRICES["claude-opus-5"]

# 실제 모델 호출이 아닌 합성 항목
SYNTHETIC = {"<synthetic>", "", None}


def normalize(model: str | None) -> str:
    """기록된 모델 문자열을 단가표 키로 정규화한다."""
    if not model:
        return ""
    m = model.strip().lower()
    if m in _ALIASES:
        return _ALIASES[m]
    if m in _PRICES:
        return m
    # claude-opus-5-20260401 처럼 날짜 접미사가 붙은 경우 가장 긴 접두사 매칭
    best = ""
    for key in _PRICES:
        if m.startswith(key) and len(key) > len(best):
            best = key
    return best or m


def price_of(model: str | None) -> tuple[float, float, float]:
    return _PRICES.get(normalize(model), _FALLBACK)


def cost_usd(model: str | None, inp: int, out: int, cw5: int, cw1h: int, cr: int) -> float:
    """단일 요청의 환산 비용(USD)."""
    if model in SYNTHETIC:
        return 0.0
    p_in, p_out, p_read = price_of(model)
    return (
        inp * p_in
        + out * p_out
        + cw5 * p_in * CACHE_WRITE_5M
        + cw1h * p_in * CACHE_WRITE_1H
        + cr * p_read
    ) / 1_000_000


def display_name(model: str | None) -> str:
    """말풍선에 보여줄 짧은 이름."""
    m = normalize(model)
    if not m or m in SYNTHETIC:
        return "기타"
    m = m.removeprefix("claude-")
    parts = m.split("-")
    family = parts[0].capitalize()
    version = ".".join(parts[1:]) if len(parts) > 1 else ""
    return f"{family} {version}".strip()
