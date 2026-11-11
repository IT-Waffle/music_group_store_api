import uuid

from fastapi import HTTPException, status

from .models import ContentType
from .repository import EngagementRepository


def engagement_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


class EngagementService:
    def __init__(self, repository: EngagementRepository):
        self.repository = repository

    async def register_view(self, target_type: ContentType, target_id: uuid.UUID) -> int:
        # Views are intentionally non-unique and unthrottled (client requirement);
        # the only rule is that the item must be publicly visible.
        if not await self.repository.is_public(target_type, target_id):
            raise engagement_error(
                status.HTTP_404_NOT_FOUND,
                "CONTENT_NOT_FOUND",
                "Content not found.",
            )
        count = await self.repository.increment_view(target_type, target_id)
        await self.repository.commit()
        return count
