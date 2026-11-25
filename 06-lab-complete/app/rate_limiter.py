"""
Rate limiting (tiêu chí 7) — sliding window lưu trong Redis.
"""
import time
import uuid
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Giới hạn RATE_LIMIT_PER_MINUTE request / 60s cho mỗi API key."""
    if r is None:
        return
    now = time.time()
    redis_key = f"ratelimit:{key}"
    member = f"{now}:{uuid.uuid4().hex[:8]}"
    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - WINDOW_SECONDS)
        pipe.zcard(redis_key)
        _, count = pipe.execute()

        if count >= settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )

        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS + 5)
        pipe.execute()
    except HTTPException:
        raise
    except Exception:
        # Fail open nếu Redis tạm thời mất kết nối
        return
