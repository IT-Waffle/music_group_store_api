import hashlib
import logging

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


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


class CommentRateLimiter:
    """Fixed-window limit of comment submissions per client IP.

    Counts every attempt (increment first, so concurrent requests can't slip
    through). Fails open: if Redis is unavailable the comment is still
    accepted, because losing a real visitor's comment is worse than a burst
    of spam that moderation will delete anyway.
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    @staticmethod
    def _key(request: Request) -> str:
        client_ip = request.client.host if request.client else "unknown"
        return f"comments:create:{client_ip}"

    async def hit(self, request: Request) -> None:
        key = self._key(request)
        try:
            attempts = int(await self.redis.incr(key))
            if attempts == 1:
                await self.redis.expire(key, settings.COMMENT_RATE_LIMIT_WINDOW_SECONDS)
            if attempts <= settings.COMMENT_RATE_LIMIT_ATTEMPTS:
                return
            retry_after = max(int(await self.redis.ttl(key)), 1)
        except RedisError:
            logger.warning("Comment rate limiter unavailable, allowing request")
            return
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMITED",
                "message": "Too many comments. Try again later.",
            },
            headers={"Retry-After": str(retry_after)},
        )
