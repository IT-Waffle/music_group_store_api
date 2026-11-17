import logging
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as aioredis

from app.infrastructure.session import get_db
from app.infrastructure.cache import get_redis
from app.domain.system.metrics import collect_system_metrics
from app.domain.system.schemas import SystemMetrics
from app.domain.users.dependencies import get_admin
from app.domain.users.models import User

router = APIRouter(prefix="/health", tags=["System"])
metrics_router = APIRouter(prefix="/api/v1/system", tags=["System"])
logger = logging.getLogger(__name__)

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
    except Exception:
        # Details go to the log only: this endpoint is public.
        logger.exception("Readiness check: database unavailable")
        errors["database"] = "unavailable"

    # Checking Redis
    try:
        await redis_cl.ping()
    except Exception:
        logger.exception("Readiness check: redis unavailable")
        errors["redis"] = "unavailable"

    if errors:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unready", "errors": errors},
        )

    return {"status": "ready"}


@metrics_router.get("/metrics", response_model=SystemMetrics)
async def get_system_metrics(
    response: Response,
    _current_user: User = Depends(get_admin),
) -> SystemMetrics:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return await collect_system_metrics()


