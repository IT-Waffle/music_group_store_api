import hashlib

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis

from app.core.config import settings


class LoginRateLimiter:
    """Fixed-window limiter for failed login attempts."""

    def __init__(self, redis: Redis):
        self.redis = redis

    @staticmethod
    def _key(request: Request, username: str) -> str:
        client_ip = request.client.host if request.client else "unknown"
        normalized_username = username.strip().lower()
        username_hash = hashlib.sha256(normalized_username.encode("utf-8")).hexdigest()
        return f"auth:login:{client_ip}:{username_hash}"

    async def ensure_allowed(self, request: Request, username: str) -> str:
        key = self._key(request, username)
        attempts = int(await self.redis.get(key) or 0)
        if attempts >= settings.AUTH_RATE_LIMIT_ATTEMPTS:
            retry_after = max(await self.redis.ttl(key), 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "RATE_LIMITED",
                    "message": "Too many failed login attempts. Try again later.",
                },
                headers={"Retry-After": str(retry_after)},
            )
        return key

    async def record_failure(self, key: str) -> None:
        attempts = await self.redis.incr(key)
        if attempts == 1:
            await self.redis.expire(key, settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)

    async def reset(self, key: str) -> None:
        await self.redis.delete(key)
