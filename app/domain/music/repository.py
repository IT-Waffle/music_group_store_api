import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.localization.models import Translation

from .models import AssetKind, MusicAsset, MusicClip, MusicTrack, TrackStatus


TRACK_LOAD_OPTIONS = (
    selectinload(MusicTrack.assets),
    selectinload(MusicTrack.clips).selectinload(MusicClip.assets),
)


class MusicRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def create_track(self, track: MusicTrack) -> MusicTrack:
        self.session.add(track)
        await self.session.flush()
        return track

    async def get_track(self, track_id: uuid.UUID) -> MusicTrack | None:
        stmt = (
            select(MusicTrack)
            .where(MusicTrack.id == track_id)
            .options(*TRACK_LOAD_OPTIONS)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_track_by_slug(
        self, slug: str, published_only: bool = False
    ) -> MusicTrack | None:
        stmt = select(MusicTrack).where(MusicTrack.slug == slug)
        if published_only:
            stmt = stmt.where(MusicTrack.status == TrackStatus.PUBLISHED.value)
        stmt = stmt.options(*TRACK_LOAD_OPTIONS)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_tracks(
        self,
        limit: int,
        offset: int,
        status_filter: TrackStatus | None = None,
        published_only: bool = False,
    ) -> tuple[list[MusicTrack], int]:
        filters = []
        if published_only:
            filters.append(MusicTrack.status == TrackStatus.PUBLISHED.value)
            filters.append(
                MusicTrack.assets.any(MusicAsset.kind == AssetKind.AUDIO.value)
            )
        elif status_filter is not None:
            filters.append(MusicTrack.status == status_filter.value)

        count_stmt = select(func.count(MusicTrack.id)).where(*filters)
        total = int((await self.session.execute(count_stmt)).scalar_one())
        stmt = (
            select(MusicTrack)
            .where(*filters)
            .options(*TRACK_LOAD_OPTIONS)
            .order_by(
                MusicTrack.sort_order.asc(),
                desc(MusicTrack.release_date).nullslast(),
                MusicTrack.created_at.desc(),
                MusicTrack.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        tracks = list((await self.session.execute(stmt)).scalars().unique().all())
        return tracks, total

    async def create_clip(self, clip: MusicClip) -> MusicClip:
        self.session.add(clip)
        await self.session.flush()
        return clip

    async def get_clip(self, clip_id: uuid.UUID) -> MusicClip | None:
        stmt = (
            select(MusicClip)
            .where(MusicClip.id == clip_id)
            .options(
                selectinload(MusicClip.assets),
                selectinload(MusicClip.track),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_public_clips(
        self, limit: int, offset: int
    ) -> tuple[list[MusicClip], int]:
        filters = (
            MusicClip.is_published.is_(True),
            MusicTrack.status == TrackStatus.PUBLISHED.value,
            MusicClip.assets.any(MusicAsset.kind == AssetKind.VIDEO.value),
        )
        count_stmt = (
            select(func.count(MusicClip.id))
            .join(MusicTrack, MusicTrack.id == MusicClip.track_id)
            .where(*filters)
        )
        total = int((await self.session.execute(count_stmt)).scalar_one())
        stmt = (
            select(MusicClip)
            .join(MusicTrack, MusicTrack.id == MusicClip.track_id)
            .where(*filters)
            .options(
                selectinload(MusicClip.assets),
                selectinload(MusicClip.track),
            )
            .order_by(
                MusicClip.sort_order.asc(),
                MusicClip.created_at.desc(),
                MusicClip.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        clips = list((await self.session.execute(stmt)).scalars().unique().all())
        return clips, total

    async def get_public_clip(self, clip_id: uuid.UUID) -> MusicClip | None:
        stmt = (
            select(MusicClip)
            .join(MusicTrack, MusicTrack.id == MusicClip.track_id)
            .where(
                MusicClip.id == clip_id,
                MusicClip.is_published.is_(True),
                MusicTrack.status == TrackStatus.PUBLISHED.value,
                MusicClip.assets.any(MusicAsset.kind == AssetKind.VIDEO.value),
            )
            .options(
                selectinload(MusicClip.assets),
                selectinload(MusicClip.track),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_asset(self, asset_id: uuid.UUID) -> MusicAsset | None:
        stmt = (
            select(MusicAsset)
            .where(MusicAsset.id == asset_id)
            .options(
                selectinload(MusicAsset.track),
                selectinload(MusicAsset.clip).selectinload(MusicClip.track),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def replace_asset(
        self,
        *,
        kind: AssetKind,
        storage_key: str,
        original_filename: str,
        content_type: str,
        size_bytes: int,
        duration_ms: int | None,
        width: int | None,
        height: int | None,
        codec: str | None,
        track_id: uuid.UUID | None = None,
        clip_id: uuid.UUID | None = None,
    ) -> tuple[MusicAsset, str | None]:
        filters = [MusicAsset.kind == kind.value]
        if track_id is not None:
            filters.append(MusicAsset.track_id == track_id)
        else:
            filters.append(MusicAsset.clip_id == clip_id)
        existing = (
            await self.session.execute(select(MusicAsset).where(*filters))
        ).scalar_one_or_none()
        old_storage_key = existing.storage_key if existing else None
        if existing:
            await self.session.delete(existing)
            await self.session.flush()

        asset = MusicAsset(
            track_id=track_id,
            clip_id=clip_id,
            kind=kind.value,
            storage_key=storage_key,
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            duration_ms=duration_ms,
            width=width,
            height=height,
            codec=codec,
        )
        self.session.add(asset)
        await self.session.flush()
        return asset, old_storage_key

    async def delete_asset(self, asset: MusicAsset) -> None:
        await self.session.delete(asset)
        await self.session.flush()

    async def delete_track(self, track: MusicTrack) -> None:
        clip_ids = [str(clip.id) for clip in track.clips]
        await self.session.execute(
            delete(Translation).where(
                Translation.entity_type == "music_track",
                Translation.entity_id == str(track.id),
            )
        )
        if clip_ids:
            await self.session.execute(
                delete(Translation).where(
                    Translation.entity_type == "music_clip",
                    Translation.entity_id.in_(clip_ids),
                )
            )
        await self.session.delete(track)

    async def delete_clip(self, clip: MusicClip) -> None:
        await self.session.execute(
            delete(Translation).where(
                Translation.entity_type == "music_clip",
                Translation.entity_id == str(clip.id),
            )
        )
        await self.session.delete(clip)

    async def get_translations(
        self, entity_type: str, entity_ids: Iterable[uuid.UUID]
    ) -> dict[str, dict[str, dict[str, str]]]:
        ids = [str(entity_id) for entity_id in entity_ids]
        if not ids:
            return {}
        stmt = select(Translation).where(
            Translation.entity_type == entity_type,
            Translation.entity_id.in_(ids),
            Translation.lang.in_(("en", "lv", "ru")),
            Translation.key.in_(("title", "description")),
        )
        translations = (await self.session.execute(stmt)).scalars().all()
        result: dict[str, dict[str, dict[str, str]]] = {}
        for item in translations:
            result.setdefault(item.entity_id, {}).setdefault(item.lang, {})[
                item.key
            ] = item.value
        return result

    async def set_translations(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        values: dict[str, dict[str, Any]],
    ) -> None:
        if not values:
            return
        entity_id_str = str(entity_id)
        existing_stmt = select(Translation).where(
            Translation.entity_type == entity_type,
            Translation.entity_id == entity_id_str,
            Translation.lang.in_(tuple(values)),
        )
        existing = (await self.session.execute(existing_stmt)).scalars().all()
        by_key = {(item.lang, item.key): item for item in existing}

        for lang, texts in values.items():
            for key, value in texts.items():
                if key not in {"title", "description"}:
                    continue
                item = by_key.get((lang, key))
                if value is None:
                    if item is not None:
                        await self.session.delete(item)
                    continue
                if item is not None:
                    item.value = value
                else:
                    self.session.add(
                        Translation(
                            entity_type=entity_type,
                            entity_id=entity_id_str,
                            lang=lang,
                            key=key,
                            value=value,
                        )
                    )
        await self.session.flush()
