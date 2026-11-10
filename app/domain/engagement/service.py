import uuid

from fastapi import HTTPException, status

from . import schemas
from .models import Comment, CommentStatus, ContentType
from .repository import EngagementRepository

SUPPORTED_LANGUAGES = ("en", "lv", "ru")


def engagement_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def normalize_language(language: str) -> str:
    normalized = language.split(",", 1)[0].split("-", 1)[0].strip().lower()
    return normalized if normalized in SUPPORTED_LANGUAGES else "en"


class EngagementService:
    def __init__(self, repository: EngagementRepository):
        self.repository = repository

    # ---- views ------------------------------------------------------------

    async def register_view(self, target_type: ContentType, target_id: uuid.UUID) -> int:
        # Views are intentionally non-unique and unthrottled (client requirement);
        # the only rule is that the item must be publicly visible.
        await self._ensure_public(target_type, target_id)
        count = await self.repository.increment_view(target_type, target_id)
        await self.repository.commit()
        return count

    # ---- comments: public ---------------------------------------------------

    async def submit_comment(
        self,
        target_type: ContentType,
        target_id: uuid.UUID,
        data: schemas.CommentCreate,
    ) -> Comment | None:
        """Store a pending comment. Returns None when the honeypot caught a bot."""
        await self._ensure_public(target_type, target_id)
        if data.website and data.website.strip():
            return None
        comment = await self.repository.add_comment(
            Comment(
                target_type=target_type.value,
                target_id=target_id,
                author_name=data.author_name,
                body=data.body,
                status=CommentStatus.PENDING.value,
            )
        )
        await self.repository.commit()
        return comment

    async def list_public_comments(
        self, target_type: ContentType, target_id: uuid.UUID, limit: int, offset: int
    ) -> schemas.CommentListResponse:
        await self._ensure_public(target_type, target_id)
        comments, total = await self.repository.list_comments(
            limit=limit,
            offset=offset,
            status=CommentStatus.APPROVED,
            target_type=target_type,
            target_id=target_id,
        )
        return schemas.CommentListResponse(
            items=[schemas.CommentPublicResponse.model_validate(c) for c in comments],
            total=total,
            limit=limit,
            offset=offset,
        )

    # ---- comments: moderation --------------------------------------------

    async def list_admin_comments(
        self,
        *,
        language: str,
        limit: int,
        offset: int,
        status_filter: CommentStatus | None,
        target_type: ContentType | None,
        target_id: uuid.UUID | None,
    ) -> schemas.AdminCommentListResponse:
        comments, total = await self.repository.list_comments(
            limit=limit,
            offset=offset,
            status=status_filter,
            target_type=target_type,
            target_id=target_id,
        )
        return schemas.AdminCommentListResponse(
            items=await self._admin_responses(comments, language),
            total=total,
            limit=limit,
            offset=offset,
        )

    async def approve_comment(
        self, comment_id: uuid.UUID, language: str
    ) -> schemas.CommentAdminResponse:
        comment = await self._required_comment(comment_id)
        # Approving twice is harmless and keeps the original approval date.
        if comment.status != CommentStatus.APPROVED.value:
            comment = await self.repository.approve_comment(comment)
            await self.repository.commit()
        return (await self._admin_responses([comment], language))[0]

    async def delete_comment(self, comment_id: uuid.UUID) -> None:
        comment = await self._required_comment(comment_id)
        await self.repository.delete_comment(comment)
        await self.repository.commit()

    async def get_target_title(
        self, target_type: ContentType, target_id: uuid.UUID, language: str
    ) -> str:
        titles = await self.repository.get_titles([(target_type, target_id)], language)
        return titles.get((target_type, target_id), "")

    # ---- helpers ----------------------------------------------------------

    async def _ensure_public(self, target_type: ContentType, target_id: uuid.UUID) -> None:
        if not await self.repository.is_public(target_type, target_id):
            raise engagement_error(
                status.HTTP_404_NOT_FOUND, "CONTENT_NOT_FOUND", "Content not found."
            )

    async def _required_comment(self, comment_id: uuid.UUID) -> Comment:
        comment = await self.repository.get_comment(comment_id)
        if comment is None:
            raise engagement_error(
                status.HTTP_404_NOT_FOUND, "COMMENT_NOT_FOUND", "Comment not found."
            )
        return comment

    async def _admin_responses(
        self, comments: list[Comment], language: str
    ) -> list[schemas.CommentAdminResponse]:
        titles = await self.repository.get_titles(
            ((ContentType(c.target_type), c.target_id) for c in comments), language
        )
        return [
            schemas.CommentAdminResponse(
                id=c.id,
                target_type=ContentType(c.target_type),
                target_id=c.target_id,
                target_title=titles.get((ContentType(c.target_type), c.target_id), ""),
                author_name=c.author_name,
                body=c.body,
                status=CommentStatus(c.status),
                created_at=c.created_at,
                approved_at=c.approved_at,
            )
            for c in comments
        ]
