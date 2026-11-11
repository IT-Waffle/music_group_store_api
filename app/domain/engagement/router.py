import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.session import get_db

from . import schemas
from .models import ContentType
from .repository import EngagementRepository
from .service import EngagementService

router = APIRouter(prefix="/engagement", tags=["Engagement"])


def get_engagement_service(session: AsyncSession = Depends(get_db)) -> EngagementService:
    return EngagementService(EngagementRepository(session))


@router.post(
    "/{target_type}/{target_id}/views",
    response_model=schemas.ViewCountResponse,
)
async def register_view(
    target_type: ContentType,
    target_id: uuid.UUID,
    service: EngagementService = Depends(get_engagement_service),
):
    """Count one (non-unique) view of a published product, track or clip."""
    return schemas.ViewCountResponse(
        view_count=await service.register_view(target_type, target_id)
    )
