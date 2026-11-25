"""
Cost guard (tiêu chí 8) — cộng dồn chi phí LLM vào Redis.
"""
import time
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _daily_key() -> str:
    return f"cost:daily:{time.strftime('%Y-%m-%d', time.gmtime())}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    if r is None:
        return
    try:
        raw = r.get(_daily_key())
        spent = float(raw) if raw is not None else 0.0
    except Exception:
        return
    budget = min(settings.daily_budget_usd, settings.monthly_budget_usd)
    if spent >= budget:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Budget exceeded",
                "spent_usd": round(spent, 6),
                "budget_usd": budget,
            },
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (
        output_tokens / 1000.0
    ) * PRICE_OUTPUT_PER_1K
    if r is not None:
        try:
            key = _daily_key()
            pipe = r.pipeline()
            pipe.incrbyfloat(key, cost)
            pipe.expire(key, 172800)
            pipe.execute()
        except Exception:
            pass
    return round(cost, 8)
