import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    Query,
    Request,
    Response,
    status,
)
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rate_limit import CommentRateLimiter
from app.domain.users.dependencies import get_moderator
from app.domain.users.models import User
from app.infrastructure.cache import get_redis
from app.infrastructure.email import BrevoEmailSender, get_email_sender
from app.infrastructure.session import get_db, get_session_factory

from . import schemas
from .models import CommentStatus, ContentType
from .notifications import notify_new_comment
from .repository import EngagementRepository
from .service import EngagementService, normalize_language

router = APIRouter(prefix="/engagement", tags=["Engagement"])


def get_engagement_service(session: AsyncSession = Depends(get_db)) -> EngagementService:
    return EngagementService(EngagementRepository(session))


# ---- moderation (moderator/admin) -----------------------------------------
# Declared before the /{target_type}/... routes so "manage" is never parsed
# as a content type.


@router.get("/manage/comments", response_model=schemas.AdminCommentListResponse)
async def list_comments_for_moderation(
    status_filter: CommentStatus | None = Query(default=CommentStatus.PENDING, alias="status"),
    target_type: ContentType | None = Query(default=None),
    target_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    accept_language: str = Header(default="en", alias="Accept-Language"),
    service: EngagementService = Depends(get_engagement_service),
    current_user: User = Depends(get_moderator),
):
    """Moderation queue, newest first. Defaults to pending comments."""
    return await service.list_admin_comments(
        language=normalize_language(accept_language),
        limit=limit,
        offset=offset,
        status_filter=status_filter,
        target_type=target_type,
        target_id=target_id,
    )


@router.post(
    "/manage/comments/{comment_id}/approve",
    response_model=schemas.CommentAdminResponse,
)
async def approve_comment(
    comment_id: uuid.UUID,
    accept_language: str = Header(default="en", alias="Accept-Language"),
    service: EngagementService = Depends(get_engagement_service),
    current_user: User = Depends(get_moderator),
):
    return await service.approve_comment(comment_id, normalize_language(accept_language))


@router.delete("/manage/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: uuid.UUID,
    service: EngagementService = Depends(get_engagement_service),
    current_user: User = Depends(get_moderator),
):
    """Reject or remove a comment. It is deleted permanently."""
    await service.delete_comment(comment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- public ---------------------------------------------------------------


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


@router.post(
    "/{target_type}/{target_id}/comments",
    response_model=schemas.CommentSubmittedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_comment(
    target_type: ContentType,
    target_id: uuid.UUID,
    data: schemas.CommentCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    service: EngagementService = Depends(get_engagement_service),
    redis: Redis = Depends(get_redis),
    email_sender: BrevoEmailSender | None = Depends(get_email_sender),
    session_factory: async_sessionmaker = Depends(get_session_factory),
):
    """Leave a comment. It stays hidden until a moderator approves it.

    The owner is emailed after the response is sent; email problems never
    affect the stored comment.
    """
    await CommentRateLimiter(redis).hit(request)
    comment = await service.submit_comment(target_type, target_id, data)
    if comment is not None and email_sender is not None:
        background_tasks.add_task(
            notify_new_comment, comment.id, session_factory, email_sender
        )
    return schemas.CommentSubmittedResponse()


@router.get(
    "/{target_type}/{target_id}/comments",
    response_model=schemas.CommentListResponse,
)
async def list_comments(
    target_type: ContentType,
    target_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: EngagementService = Depends(get_engagement_service),
):
    """Approved comments of a published item, newest first."""
    return await service.list_public_comments(target_type, target_id, limit, offset)
