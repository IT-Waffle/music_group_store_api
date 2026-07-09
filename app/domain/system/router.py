from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as aioredis

from app.infrastructure.session import get_db
from app.infrastructure.cache import get_redis

router = APIRouter(prefix="/health", tags=["System"])


@router.get("/live", status_code=status.HTTP_200_OK)
async def health_live():
    """Checking that the application is alive (basic liveness check)"""
    return {"status": "alive"}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def health_ready(
    db: AsyncSession = Depends(get_db), redis_cl: aioredis.Redis = Depends(get_redis)
):
    """Checking that the application is ready to serve requests (DB and Redis are reachable)"""
    errors = {}

    # Checking Postgres
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        errors["database"] = str(e)

    # Checking Redis
    try:
        await redis_cl.ping()
    except Exception as e:
        errors["redis"] = str(e)

    if errors:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unready", "errors": errors},
        )

    return {"status": "ready"}
