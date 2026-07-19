import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

from fastapi import HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from . import schemas
from .models import AssetKind, MusicAsset, MusicClip, MusicTrack, TrackStatus
from .repository import MusicRepository
from .storage import LocalMusicStorage, MediaValidationError

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("en", "lv", "ru")


def music_error(
    status_code: int, code: str, message: str, field: str | None = None
) -> HTTPException:
    detail: dict[str, str] = {"code": code, "message": message}
    if field:
        detail["field"] = field
    return HTTPException(status_code=status_code, detail=detail)


class MusicService:
    def __init__(
        self,
        repository: MusicRepository,
        storage: LocalMusicStorage | None = None,
    ):
        self.repository = repository
        self.storage = storage or LocalMusicStorage()

    @staticmethod
    def normalize_language(language: str) -> str:
        normalized = language.split(",", 1)[0].split("-", 1)[0].strip().lower()
        return normalized if normalized in SUPPORTED_LANGUAGES else "en"

    async def create_track(
        self, data: schemas.MusicTrackCreate
    ) -> schemas.MusicTrackAdminResponse:
        track = MusicTrack(
            slug=data.slug,
            status=TrackStatus.DRAFT.value,
            sort_order=data.sort_order,
            release_date=data.release_date,
        )
        try:
            await self.repository.create_track(track)
            await self.repository.set_translations(
                "music_track", track.id, self._translation_values(data.translations)
            )
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise music_error(
                status.HTTP_409_CONFLICT,
                "TRACK_SLUG_CONFLICT",
                "A track with this slug already exists.",
                "slug",
            ) from exc
        track = await self._required_track(track.id)
        return await self._track_admin_response(track)

    async def update_track(
        self,
        track_id: uuid.UUID,
        data: schemas.MusicTrackUpdate,
        *,
        is_admin: bool,
    ) -> schemas.MusicTrackAdminResponse:
        track = await self._required_track(track_id)
        self._ensure_can_modify(track, is_admin)
        fields = data.model_fields_set
        if "slug" in fields:
            if data.slug is not None:
                track.slug = data.slug
        if "sort_order" in fields:
            if data.sort_order is not None:
                track.sort_order = data.sort_order
        if "release_date" in fields:
            track.release_date = data.release_date
        self._touch(track)
        try:
            if data.translations is not None:
                await self.repository.set_translations(
                    "music_track",
                    track.id,
                    self._translation_values(data.translations),
                )
            if track.status == TrackStatus.PUBLISHED.value:
                await self.repository.session.flush()
                translations = await self.repository.get_translations(
                    "music_track", [track.id]
                )
                self._ensure_complete_translations(
                    translations.get(str(track.id), {}), "track"
                )
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise music_error(
                status.HTTP_409_CONFLICT,
                "TRACK_SLUG_CONFLICT",
                "A track with this slug already exists.",
                "slug",
            ) from exc
        return await self._track_admin_response(await self._required_track(track_id))

    async def publish_track(
        self, track_id: uuid.UUID
    ) -> schemas.MusicTrackAdminResponse:
        track = await self._required_track(track_id)
        if track.status == TrackStatus.ARCHIVED.value:
            raise music_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_STATE_TRANSITION",
                "Restore the track before publishing it.",
            )
        translations = await self.repository.get_translations("music_track", [track.id])
        self._ensure_complete_translations(translations.get(str(track.id), {}), "track")
        audio = self._asset(track.assets, AssetKind.AUDIO)
        if not audio or not self.storage.exists(audio.storage_key):
            raise music_error(
                status.HTTP_409_CONFLICT,
                "TRACK_AUDIO_REQUIRED",
                "Upload a valid audio file before publishing the track.",
                "audio",
            )
        published_clips = [clip for clip in track.clips if clip.is_published]
        clip_translations = await self.repository.get_translations(
            "music_clip", [clip.id for clip in published_clips]
        )
        for clip in published_clips:
            video = self._asset(clip.assets, AssetKind.VIDEO)
            if not video or not self.storage.exists(video.storage_key):
                raise music_error(
                    status.HTTP_409_CONFLICT,
                    "CLIP_VIDEO_REQUIRED",
                    "Every published clip must have a valid uploaded MP4.",
                    "clips",
                )
            self._ensure_complete_translations(
                clip_translations.get(str(clip.id), {}), "clip"
            )
        track.status = TrackStatus.PUBLISHED.value
        track.published_at = datetime.now(timezone.utc)
        await self.repository.commit()
        return await self._track_admin_response(await self._required_track(track_id))

    async def unpublish_track(
        self, track_id: uuid.UUID
    ) -> schemas.MusicTrackAdminResponse:
        track = await self._required_track(track_id)
        if track.status != TrackStatus.PUBLISHED.value:
            raise music_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_STATE_TRANSITION",
                "Only a published track can be unpublished.",
            )
        track.status = TrackStatus.DRAFT.value
        track.published_at = None
        await self.repository.commit()
        return await self._track_admin_response(await self._required_track(track_id))

    async def archive_track(
        self, track_id: uuid.UUID
    ) -> schemas.MusicTrackAdminResponse:
        track = await self._required_track(track_id)
        if track.status == TrackStatus.ARCHIVED.value:
            raise music_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_STATE_TRANSITION",
                "The track is already archived.",
            )
        track.status = TrackStatus.ARCHIVED.value
        track.published_at = None
        await self.repository.commit()
        return await self._track_admin_response(await self._required_track(track_id))

    async def restore_track(
        self, track_id: uuid.UUID
    ) -> schemas.MusicTrackAdminResponse:
        track = await self._required_track(track_id)
        if track.status != TrackStatus.ARCHIVED.value:
            raise music_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_STATE_TRANSITION",
                "Only an archived track can be restored.",
            )
        track.status = TrackStatus.DRAFT.value
        await self.repository.commit()
        return await self._track_admin_response(await self._required_track(track_id))

    async def delete_track(self, track_id: uuid.UUID) -> None:
        track = await self._required_track(track_id)
        if track.status == TrackStatus.PUBLISHED.value:
            raise music_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_STATE_TRANSITION",
                "Unpublish or archive the track before deleting it.",
            )
        storage_keys = [asset.storage_key for asset in track.assets]
        storage_keys.extend(
            asset.storage_key for clip in track.clips for asset in clip.assets
        )
        await self.repository.delete_track(track)
        await self.repository.commit()
        await self._delete_files(storage_keys)

    async def list_public_tracks(
        self, language: str, limit: int, offset: int
    ) -> schemas.TrackListResponse:
        tracks, total = await self.repository.list_tracks(
            limit, offset, published_only=True
        )
        track_translations = await self.repository.get_translations(
            "music_track", [track.id for track in tracks]
        )
        clip_ids = [clip.id for track in tracks for clip in track.clips]
        clip_translations = await self.repository.get_translations(
            "music_clip", clip_ids
        )
        items = []
        for track in tracks:
            response = self._track_public_response(
                track, language, track_translations, clip_translations
            )
            if response is not None:
                items.append(response)
        return schemas.TrackListResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    async def get_public_track(
        self, slug: str, language: str
    ) -> schemas.MusicTrackPublicResponse:
        track = await self.repository.get_track_by_slug(slug, published_only=True)
        if not track:
            raise self._track_not_found()
        track_translations = await self.repository.get_translations(
            "music_track", [track.id]
        )
        clip_translations = await self.repository.get_translations(
            "music_clip", [clip.id for clip in track.clips]
        )
        response = self._track_public_response(
            track, language, track_translations, clip_translations
        )
        if response is None:
            raise self._track_not_found()
        return response

    async def list_admin_tracks(
        self,
        limit: int,
        offset: int,
        status_filter: TrackStatus | None,
    ) -> schemas.AdminTrackListResponse:
        tracks, total = await self.repository.list_tracks(
            limit, offset, status_filter=status_filter
        )
        track_translations = await self.repository.get_translations(
            "music_track", [track.id for track in tracks]
        )
        clip_translations = await self.repository.get_translations(
            "music_clip", [clip.id for track in tracks for clip in track.clips]
        )
        items = [
            self._track_admin_response_sync(
                track,
                track_translations.get(str(track.id), {}),
                clip_translations,
            )
            for track in tracks
        ]
        return schemas.AdminTrackListResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    async def get_admin_track(
        self, track_id: uuid.UUID
    ) -> schemas.MusicTrackAdminResponse:
        return await self._track_admin_response(await self._required_track(track_id))

    async def create_clip(
        self,
        track_id: uuid.UUID,
        data: schemas.MusicClipCreate,
        *,
        is_admin: bool,
    ) -> schemas.MusicClipAdminResponse:
        track = await self._required_track(track_id)
        self._ensure_can_modify(track, is_admin)
        youtube_url = self._validate_external_url(data.youtube_url, "youtube")
        vimeo_url = self._validate_external_url(data.vimeo_url, "vimeo")
        clip = MusicClip(
            track_id=track.id,
            sort_order=data.sort_order,
            is_published=False,
            youtube_url=youtube_url,
            vimeo_url=vimeo_url,
        )
        self._touch(track)
        await self.repository.create_clip(clip)
        await self.repository.set_translations(
            "music_clip", clip.id, self._translation_values(data.translations)
        )
        await self.repository.commit()
        return await self._clip_admin_response(await self._required_clip(clip.id))

    async def update_clip(
        self,
        track_id: uuid.UUID,
        clip_id: uuid.UUID,
        data: schemas.MusicClipUpdate,
        *,
        is_admin: bool,
    ) -> schemas.MusicClipAdminResponse:
        track = await self._required_track(track_id)
        self._ensure_can_modify(track, is_admin)
        clip = await self._required_clip(clip_id, track_id=track.id)
        fields = data.model_fields_set
        if "sort_order" in fields:
            if data.sort_order is not None:
                clip.sort_order = data.sort_order
        if "youtube_url" in fields:
            clip.youtube_url = self._validate_external_url(data.youtube_url, "youtube")
        if "vimeo_url" in fields:
            clip.vimeo_url = self._validate_external_url(data.vimeo_url, "vimeo")
        if data.translations is not None:
            await self.repository.set_translations(
                "music_clip", clip.id, self._translation_values(data.translations)
            )
        self._touch(clip)
        self._touch(track)
        target_published = (
            data.is_published
            if "is_published" in fields and data.is_published is not None
            else clip.is_published
        )
        if target_published:
            video = self._asset(clip.assets, AssetKind.VIDEO)
            if not video or not self.storage.exists(video.storage_key):
                raise music_error(
                    status.HTTP_409_CONFLICT,
                    "CLIP_VIDEO_REQUIRED",
                    "Upload a valid MP4 before publishing the clip.",
                    "video",
                )
            # Include uncommitted translation updates before validating.
            await self.repository.session.flush()
            translations = await self.repository.get_translations(
                "music_clip", [clip.id]
            )
            self._ensure_complete_translations(
                translations.get(str(clip.id), {}), "clip"
            )
            clip.is_published = True
        else:
            clip.is_published = False
        await self.repository.commit()
        return await self._clip_admin_response(await self._required_clip(clip.id))

    async def delete_clip(
        self, track_id: uuid.UUID, clip_id: uuid.UUID, *, is_admin: bool
    ) -> None:
        track = await self._required_track(track_id)
        self._ensure_can_modify(track, is_admin)
        clip = await self._required_clip(clip_id, track_id=track.id)
        storage_keys = [asset.storage_key for asset in clip.assets]
        self._touch(track)
        await self.repository.delete_clip(clip)
        await self.repository.commit()
        await self._delete_files(storage_keys)

    async def list_public_clips(
        self, language: str, limit: int, offset: int
    ) -> schemas.ClipListResponse:
        clips, total = await self.repository.list_public_clips(limit, offset)
        translations = await self.repository.get_translations(
            "music_clip", [clip.id for clip in clips]
        )
        items = [
            response
            for clip in clips
            if (response := self._clip_public_response(clip, language, translations))
            is not None
        ]
        return schemas.ClipListResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    async def get_public_clip(
        self, clip_id: uuid.UUID, language: str
    ) -> schemas.MusicClipPublicResponse:
        clip = await self.repository.get_public_clip(clip_id)
        if not clip:
            raise self._clip_not_found()
        translations = await self.repository.get_translations("music_clip", [clip.id])
        response = self._clip_public_response(clip, language, translations)
        if response is None:
            raise self._clip_not_found()
        return response

    async def upload_track_asset(
        self,
        track_id: uuid.UUID,
        kind: AssetKind,
        file: UploadFile,
        *,
        is_admin: bool,
    ) -> schemas.MusicAssetAdminResponse:
        if kind not in {AssetKind.AUDIO, AssetKind.COVER}:
            raise ValueError("Invalid track asset kind")
        track = await self._required_track(track_id)
        self._ensure_can_modify(track, is_admin)
        self._touch(track)
        return await self._upload_asset(
            file=file, kind=kind, owner_id=track.id, track_id=track.id
        )

    async def upload_clip_asset(
        self,
        clip_id: uuid.UUID,
        kind: AssetKind,
        file: UploadFile,
        *,
        is_admin: bool,
    ) -> schemas.MusicAssetAdminResponse:
        if kind not in {AssetKind.VIDEO, AssetKind.POSTER}:
            raise ValueError("Invalid clip asset kind")
        clip = await self._required_clip(clip_id)
        self._ensure_can_modify(clip.track, is_admin)
        self._touch(clip)
        self._touch(clip.track)
        return await self._upload_asset(
            file=file, kind=kind, owner_id=clip.id, clip_id=clip.id
        )

    async def delete_track_asset(
        self,
        track_id: uuid.UUID,
        kind: AssetKind,
        *,
        is_admin: bool,
    ) -> None:
        track = await self._required_track(track_id)
        self._ensure_can_modify(track, is_admin)
        if kind == AssetKind.AUDIO and track.status == TrackStatus.PUBLISHED.value:
            raise music_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_STATE_TRANSITION",
                "Unpublish the track before deleting its audio.",
            )
        asset = self._asset(track.assets, kind)
        if not asset:
            raise self._asset_not_found()
        storage_key = asset.storage_key
        self._touch(track)
        await self.repository.delete_asset(asset)
        await self.repository.commit()
        await self._delete_files([storage_key])

    async def delete_clip_poster(self, clip_id: uuid.UUID, *, is_admin: bool) -> None:
        clip = await self._required_clip(clip_id)
        self._ensure_can_modify(clip.track, is_admin)
        poster = self._asset(clip.assets, AssetKind.POSTER)
        if not poster:
            raise self._asset_not_found()
        storage_key = poster.storage_key
        self._touch(clip)
        self._touch(clip.track)
        await self.repository.delete_asset(poster)
        await self.repository.commit()
        await self._delete_files([storage_key])

    async def serve_track_asset(self, slug: str, kind: AssetKind) -> Response:
        track = await self.repository.get_track_by_slug(slug, published_only=True)
        if not track:
            raise self._track_not_found()
        asset = self._asset(track.assets, kind)
        if not asset:
            raise self._asset_not_found()
        return self._file_response(asset)

    async def serve_clip_asset(self, clip_id: uuid.UUID, kind: AssetKind) -> Response:
        clip = await self.repository.get_public_clip(clip_id)
        if not clip:
            raise self._clip_not_found()
        asset = self._asset(clip.assets, kind)
        if not asset:
            raise self._asset_not_found()
        return self._file_response(asset)

    async def serve_admin_asset(self, asset_id: uuid.UUID) -> Response:
        asset = await self.repository.get_asset(asset_id)
        if not asset:
            raise self._asset_not_found()
        return self._file_response(asset)

    async def _upload_asset(
        self,
        *,
        file: UploadFile,
        kind: AssetKind,
        owner_id: uuid.UUID,
        track_id: uuid.UUID | None = None,
        clip_id: uuid.UUID | None = None,
    ) -> schemas.MusicAssetAdminResponse:
        try:
            staged = await self.storage.stage(file, kind)
        except MediaValidationError as exc:
            raise music_error(
                exc.status_code, exc.code, exc.message, kind.value
            ) from exc

        new_storage_key: str | None = None
        try:
            new_storage_key = await self.storage.promote(staged, owner_id, kind)
            metadata = staged.metadata
            asset, old_storage_key = await self.repository.replace_asset(
                track_id=track_id,
                clip_id=clip_id,
                kind=kind,
                storage_key=new_storage_key,
                original_filename=staged.original_filename,
                content_type=metadata.content_type,
                size_bytes=metadata.size_bytes,
                duration_ms=metadata.duration_ms,
                width=metadata.width,
                height=metadata.height,
                codec=metadata.codec,
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            if new_storage_key:
                await self._delete_files([new_storage_key])
            raise
        if old_storage_key:
            await self._delete_files([old_storage_key])
        return self._admin_asset_response(asset, self._admin_asset_url(asset))

    async def _required_track(self, track_id: uuid.UUID) -> MusicTrack:
        track = await self.repository.get_track(track_id)
        if not track:
            raise self._track_not_found()
        return track

    async def _required_clip(
        self, clip_id: uuid.UUID, track_id: uuid.UUID | None = None
    ) -> MusicClip:
        clip = await self.repository.get_clip(clip_id)
        if not clip or (track_id is not None and clip.track_id != track_id):
            raise self._clip_not_found()
        return clip

    @staticmethod
    def _ensure_can_modify(track: MusicTrack, is_admin: bool) -> None:
        if track.status == TrackStatus.ARCHIVED.value:
            raise music_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_STATE_TRANSITION",
                "Restore the track before modifying it.",
            )
        if track.status == TrackStatus.PUBLISHED.value and not is_admin:
            raise music_error(
                status.HTTP_403_FORBIDDEN,
                "INSUFFICIENT_ROLE",
                "Only an admin can modify a published track.",
            )

    @staticmethod
    def _touch(entity: MusicTrack | MusicClip) -> None:
        entity.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _translation_values(
        translations: schemas.TranslationsInput,
    ) -> dict[str, dict[str, str | None]]:
        return translations.model_dump(exclude_unset=True)

    @staticmethod
    def _ensure_complete_translations(
        translations: dict[str, dict[str, str]], entity: str
    ) -> None:
        missing = [
            f"{lang}.{key}"
            for lang in SUPPORTED_LANGUAGES
            for key in ("title", "description")
            if not translations.get(lang, {}).get(key, "").strip()
        ]
        if missing:
            raise music_error(
                status.HTTP_409_CONFLICT,
                "TRANSLATIONS_REQUIRED",
                f"Complete title and description in en, lv and ru before publishing the {entity}.",
                "translations",
            )

    @staticmethod
    def _validate_external_url(value: str | None, provider: str) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        parsed = urlsplit(value)
        allowed_hosts = {
            "youtube": {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"},
            "vimeo": {"vimeo.com", "www.vimeo.com", "player.vimeo.com"},
        }
        if (
            parsed.scheme != "https"
            or parsed.hostname not in allowed_hosts[provider]
            or parsed.username
            or parsed.password
        ):
            raise music_error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "INVALID_EXTERNAL_VIDEO_URL",
                f"Invalid {provider.title()} HTTPS URL.",
                f"{provider}_url",
            )
        return value

    async def _track_admin_response(
        self, track: MusicTrack
    ) -> schemas.MusicTrackAdminResponse:
        track_translations = await self.repository.get_translations(
            "music_track", [track.id]
        )
        clip_translations = await self.repository.get_translations(
            "music_clip", [clip.id for clip in track.clips]
        )
        return self._track_admin_response_sync(
            track,
            track_translations.get(str(track.id), {}),
            clip_translations,
        )

    def _track_admin_response_sync(
        self,
        track: MusicTrack,
        track_translations: dict[str, dict[str, str]],
        clip_translations: dict[str, dict[str, dict[str, str]]],
    ) -> schemas.MusicTrackAdminResponse:
        return schemas.MusicTrackAdminResponse(
            id=track.id,
            slug=track.slug,
            status=TrackStatus(track.status),
            sort_order=track.sort_order,
            release_date=track.release_date,
            published_at=track.published_at,
            translations=self._translations_response(track_translations),
            audio=self._optional_admin_asset(track.assets, AssetKind.AUDIO),
            cover=self._optional_admin_asset(track.assets, AssetKind.COVER),
            clips=[
                self._clip_admin_response_sync(
                    clip, clip_translations.get(str(clip.id), {})
                )
                for clip in track.clips
            ],
            created_at=track.created_at,
            updated_at=track.updated_at,
        )

    async def _clip_admin_response(
        self, clip: MusicClip
    ) -> schemas.MusicClipAdminResponse:
        translations = await self.repository.get_translations("music_clip", [clip.id])
        return self._clip_admin_response_sync(clip, translations.get(str(clip.id), {}))

    def _clip_admin_response_sync(
        self, clip: MusicClip, translations: dict[str, dict[str, str]]
    ) -> schemas.MusicClipAdminResponse:
        return schemas.MusicClipAdminResponse(
            id=clip.id,
            track_id=clip.track_id,
            sort_order=clip.sort_order,
            is_published=clip.is_published,
            youtube_url=clip.youtube_url,
            vimeo_url=clip.vimeo_url,
            translations=self._translations_response(translations),
            video=self._optional_admin_asset(clip.assets, AssetKind.VIDEO),
            poster=self._optional_admin_asset(clip.assets, AssetKind.POSTER),
            created_at=clip.created_at,
            updated_at=clip.updated_at,
        )

    def _track_public_response(
        self,
        track: MusicTrack,
        language: str,
        track_translations: dict[str, dict[str, dict[str, str]]],
        clip_translations: dict[str, dict[str, dict[str, str]]],
    ) -> schemas.MusicTrackPublicResponse | None:
        audio = self._asset(track.assets, AssetKind.AUDIO)
        if not audio or not self.storage.exists(audio.storage_key):
            return None
        cover = self._asset(track.assets, AssetKind.COVER)
        text = self._localized_text(track_translations.get(str(track.id), {}), language)
        clips = []
        for clip in track.clips:
            if not clip.is_published:
                continue
            response = self._clip_public_response(clip, language, clip_translations)
            if response is not None:
                clips.append(response)
        return schemas.MusicTrackPublicResponse(
            id=track.id,
            slug=track.slug,
            title=text["title"],
            description=text["description"],
            sort_order=track.sort_order,
            release_date=track.release_date,
            audio=self._asset_response(
                audio,
                f"{settings.MUSIC_MEDIA_BASE_URL.rstrip('/')}/tracks/{track.slug}/audio",
            ),
            cover=(
                self._asset_response(
                    cover,
                    f"{settings.MUSIC_MEDIA_BASE_URL.rstrip('/')}/tracks/{track.slug}/cover",
                )
                if cover and self.storage.exists(cover.storage_key)
                else None
            ),
            clips=clips,
            created_at=track.created_at,
            updated_at=track.updated_at,
        )

    def _clip_public_response(
        self,
        clip: MusicClip,
        language: str,
        translations: dict[str, dict[str, dict[str, str]]],
    ) -> schemas.MusicClipPublicResponse | None:
        video = self._asset(clip.assets, AssetKind.VIDEO)
        if not video or not self.storage.exists(video.storage_key):
            return None
        poster = self._asset(clip.assets, AssetKind.POSTER)
        text = self._localized_text(translations.get(str(clip.id), {}), language)
        return schemas.MusicClipPublicResponse(
            id=clip.id,
            track_id=clip.track_id,
            track_slug=clip.track.slug,
            title=text["title"],
            description=text["description"],
            sort_order=clip.sort_order,
            video=self._asset_response(
                video,
                f"{settings.MUSIC_MEDIA_BASE_URL.rstrip('/')}/clips/{clip.id}/video",
            ),
            poster=(
                self._asset_response(
                    poster,
                    f"{settings.MUSIC_MEDIA_BASE_URL.rstrip('/')}/clips/{clip.id}/poster",
                )
                if poster and self.storage.exists(poster.storage_key)
                else None
            ),
            youtube_url=clip.youtube_url,
            vimeo_url=clip.vimeo_url,
            created_at=clip.created_at,
            updated_at=clip.updated_at,
        )

    @staticmethod
    def _localized_text(
        translations: dict[str, dict[str, str]], language: str
    ) -> dict[str, str]:
        localized = translations.get(language, {})
        fallback = translations.get("en", {})
        return {
            "title": localized.get("title") or fallback.get("title") or "",
            "description": localized.get("description")
            or fallback.get("description")
            or "",
        }

    @staticmethod
    def _translations_response(
        translations: dict[str, dict[str, str]],
    ) -> schemas.TranslationsResponse:
        values = {
            language: schemas.TranslationTextResponse(
                title=translations.get(language, {}).get("title"),
                description=translations.get(language, {}).get("description"),
            )
            for language in SUPPORTED_LANGUAGES
        }
        return schemas.TranslationsResponse(**values)

    @staticmethod
    def _asset(assets: list[MusicAsset], kind: AssetKind) -> MusicAsset | None:
        return next((asset for asset in assets if asset.kind == kind.value), None)

    def _optional_admin_asset(
        self, assets: list[MusicAsset], kind: AssetKind
    ) -> schemas.MusicAssetAdminResponse | None:
        asset = self._asset(assets, kind)
        if not asset:
            return None
        return self._admin_asset_response(asset, self._admin_asset_url(asset))

    @staticmethod
    def _asset_response(asset: MusicAsset, url: str) -> schemas.MusicAssetResponse:
        return schemas.MusicAssetResponse(
            id=asset.id,
            kind=asset.kind,
            url=url,
            content_type=asset.content_type,
            size_bytes=asset.size_bytes,
            duration_ms=asset.duration_ms,
            width=asset.width,
            height=asset.height,
            codec=asset.codec,
        )

    @staticmethod
    def _admin_asset_response(
        asset: MusicAsset, url: str
    ) -> schemas.MusicAssetAdminResponse:
        return schemas.MusicAssetAdminResponse(
            id=asset.id,
            kind=asset.kind,
            url=url,
            content_type=asset.content_type,
            size_bytes=asset.size_bytes,
            duration_ms=asset.duration_ms,
            width=asset.width,
            height=asset.height,
            codec=asset.codec,
            original_filename=asset.original_filename,
        )

    @staticmethod
    def _admin_asset_url(asset: MusicAsset) -> str:
        return (
            f"{settings.MUSIC_MEDIA_BASE_URL.rstrip('/')}/manage/assets/"
            f"{asset.id}/content"
        )

    def _file_response(self, asset: MusicAsset) -> Response:
        path = self.storage.resolve(asset.storage_key)
        if not path.is_file():
            raise self._asset_not_found()
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        }
        if settings.MEDIA_USE_X_ACCEL_REDIRECT:
            internal_path = quote(asset.storage_key, safe="/")
            headers["X-Accel-Redirect"] = (
                f"{settings.MEDIA_X_ACCEL_PREFIX.rstrip('/')}/{internal_path}"
            )
            return Response(media_type=asset.content_type, headers=headers)
        return FileResponse(path=path, media_type=asset.content_type, headers=headers)

    async def _delete_files(self, storage_keys: list[str]) -> None:
        for key in storage_keys:
            try:
                await self.storage.delete(key)
            except Exception:
                logger.error("Failed to delete a music media object")

    @staticmethod
    def _track_not_found() -> HTTPException:
        return music_error(404, "TRACK_NOT_FOUND", "Track not found.")

    @staticmethod
    def _clip_not_found() -> HTTPException:
        return music_error(404, "CLIP_NOT_FOUND", "Clip not found.")

    @staticmethod
    def _asset_not_found() -> HTTPException:
        return music_error(404, "ASSET_NOT_FOUND", "Media asset not found.")
