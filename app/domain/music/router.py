import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.users.dependencies import get_admin, get_moderator
from app.domain.users.models import User, UserRole
from app.infrastructure.session import get_db

from . import schemas
from .models import AssetKind, TrackStatus
from .repository import MusicRepository
from .service import MusicService

router = APIRouter(prefix="/music", tags=["Music"])


def get_music_service(session: AsyncSession = Depends(get_db)) -> MusicService:
    return MusicService(MusicRepository(session))


def is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


@router.get("/tracks", response_model=schemas.TrackListResponse)
async def list_public_tracks(
    accept_language: str = Header(default="en", alias="Accept-Language"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: MusicService = Depends(get_music_service),
):
    language = service.normalize_language(accept_language)
    return await service.list_public_tracks(language, limit, offset)


@router.get("/tracks/{slug}", response_model=schemas.MusicTrackPublicResponse)
async def get_public_track(
    slug: str,
    accept_language: str = Header(default="en", alias="Accept-Language"),
    service: MusicService = Depends(get_music_service),
):
    language = service.normalize_language(accept_language)
    return await service.get_public_track(slug, language)


@router.get("/tracks/{slug}/audio")
@router.head("/tracks/{slug}/audio", include_in_schema=False)
async def get_track_audio(
    slug: str, service: MusicService = Depends(get_music_service)
):
    return await service.serve_track_asset(slug, AssetKind.AUDIO)


@router.get("/tracks/{slug}/cover")
@router.head("/tracks/{slug}/cover", include_in_schema=False)
async def get_track_cover(
    slug: str, service: MusicService = Depends(get_music_service)
):
    return await service.serve_track_asset(slug, AssetKind.COVER)


@router.get("/clips", response_model=schemas.ClipListResponse)
async def list_public_clips(
    accept_language: str = Header(default="en", alias="Accept-Language"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: MusicService = Depends(get_music_service),
):
    language = service.normalize_language(accept_language)
    return await service.list_public_clips(language, limit, offset)


@router.get("/clips/{clip_id}", response_model=schemas.MusicClipPublicResponse)
async def get_public_clip(
    clip_id: uuid.UUID,
    accept_language: str = Header(default="en", alias="Accept-Language"),
    service: MusicService = Depends(get_music_service),
):
    language = service.normalize_language(accept_language)
    return await service.get_public_clip(clip_id, language)


@router.get("/clips/{clip_id}/video")
@router.head("/clips/{clip_id}/video", include_in_schema=False)
async def get_clip_video(
    clip_id: uuid.UUID, service: MusicService = Depends(get_music_service)
):
    return await service.serve_clip_asset(clip_id, AssetKind.VIDEO)


@router.get("/clips/{clip_id}/poster")
@router.head("/clips/{clip_id}/poster", include_in_schema=False)
async def get_clip_poster(
    clip_id: uuid.UUID, service: MusicService = Depends(get_music_service)
):
    return await service.serve_clip_asset(clip_id, AssetKind.POSTER)


@router.get("/manage/tracks", response_model=schemas.AdminTrackListResponse)
async def list_admin_tracks(
    status_filter: TrackStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    return await service.list_admin_tracks(limit, offset, status_filter)


@router.get("/manage/tracks/{track_id}", response_model=schemas.MusicTrackAdminResponse)
async def get_admin_track(
    track_id: uuid.UUID,
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    return await service.get_admin_track(track_id)


@router.post(
    "/manage/tracks",
    response_model=schemas.MusicTrackAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_track(
    data: schemas.MusicTrackCreate,
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    return await service.create_track(data)


@router.patch(
    "/manage/tracks/{track_id}", response_model=schemas.MusicTrackAdminResponse
)
async def update_track(
    track_id: uuid.UUID,
    data: schemas.MusicTrackUpdate,
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    return await service.update_track(track_id, data, is_admin=is_admin(current_user))


@router.post(
    "/manage/tracks/{track_id}/publish",
    response_model=schemas.MusicTrackAdminResponse,
)
async def publish_track(
    track_id: uuid.UUID,
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_admin),
):
    return await service.publish_track(track_id)


@router.post(
    "/manage/tracks/{track_id}/unpublish",
    response_model=schemas.MusicTrackAdminResponse,
)
async def unpublish_track(
    track_id: uuid.UUID,
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    return await service.unpublish_track(track_id)


@router.post(
    "/manage/tracks/{track_id}/archive",
    response_model=schemas.MusicTrackAdminResponse,
)
async def archive_track(
    track_id: uuid.UUID,
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_admin),
):
    return await service.archive_track(track_id)


@router.post(
    "/manage/tracks/{track_id}/restore",
    response_model=schemas.MusicTrackAdminResponse,
)
async def restore_track(
    track_id: uuid.UUID,
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_admin),
):
    return await service.restore_track(track_id)


@router.delete("/manage/tracks/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_track(
    track_id: uuid.UUID,
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_admin),
):
    await service.delete_track(track_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/manage/tracks/{track_id}/audio",
    response_model=schemas.MusicAssetAdminResponse,
)
async def upload_track_audio(
    track_id: uuid.UUID,
    file: UploadFile = File(...),
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    return await service.upload_track_asset(
        track_id, AssetKind.AUDIO, file, is_admin=is_admin(current_user)
    )


@router.delete(
    "/manage/tracks/{track_id}/audio", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_track_audio(
    track_id: uuid.UUID,
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    await service.delete_track_asset(
        track_id, AssetKind.AUDIO, is_admin=is_admin(current_user)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/manage/tracks/{track_id}/cover",
    response_model=schemas.MusicAssetAdminResponse,
)
async def upload_track_cover(
    track_id: uuid.UUID,
    file: UploadFile = File(...),
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    return await service.upload_track_asset(
        track_id, AssetKind.COVER, file, is_admin=is_admin(current_user)
    )


@router.delete(
    "/manage/tracks/{track_id}/cover", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_track_cover(
    track_id: uuid.UUID,
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    await service.delete_track_asset(
        track_id, AssetKind.COVER, is_admin=is_admin(current_user)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/manage/tracks/{track_id}/clips",
    response_model=schemas.MusicClipAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_clip(
    track_id: uuid.UUID,
    data: schemas.MusicClipCreate,
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    return await service.create_clip(track_id, data, is_admin=is_admin(current_user))


@router.patch(
    "/manage/tracks/{track_id}/clips/{clip_id}",
    response_model=schemas.MusicClipAdminResponse,
)
async def update_clip(
    track_id: uuid.UUID,
    clip_id: uuid.UUID,
    data: schemas.MusicClipUpdate,
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    return await service.update_clip(
        track_id, clip_id, data, is_admin=is_admin(current_user)
    )


@router.delete(
    "/manage/tracks/{track_id}/clips/{clip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_clip(
    track_id: uuid.UUID,
    clip_id: uuid.UUID,
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    await service.delete_clip(track_id, clip_id, is_admin=is_admin(current_user))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/manage/clips/{clip_id}/video",
    response_model=schemas.MusicAssetAdminResponse,
)
async def upload_clip_video(
    clip_id: uuid.UUID,
    file: UploadFile = File(...),
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    return await service.upload_clip_asset(
        clip_id, AssetKind.VIDEO, file, is_admin=is_admin(current_user)
    )


@router.post(
    "/manage/clips/{clip_id}/poster",
    response_model=schemas.MusicAssetAdminResponse,
)
async def upload_clip_poster(
    clip_id: uuid.UUID,
    file: UploadFile = File(...),
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    return await service.upload_clip_asset(
        clip_id, AssetKind.POSTER, file, is_admin=is_admin(current_user)
    )


@router.delete("/manage/clips/{clip_id}/poster", status_code=status.HTTP_204_NO_CONTENT)
async def delete_clip_poster(
    clip_id: uuid.UUID,
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    await service.delete_clip_poster(clip_id, is_admin=is_admin(current_user))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/manage/assets/{asset_id}/content")
@router.head("/manage/assets/{asset_id}/content", include_in_schema=False)
async def preview_admin_asset(
    asset_id: uuid.UUID,
    service: MusicService = Depends(get_music_service),
    current_user: User = Depends(get_moderator),
):
    return await service.serve_admin_asset(asset_id)
