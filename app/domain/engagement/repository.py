import uuid
from collections.abc import Iterable

from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.catalog.models import Product
from app.domain.music.models import (
    AssetKind,
    MusicAsset,
    MusicClip,
    MusicTrack,
    TrackStatus,
)

from .models import ContentType, ViewCounter


async def fetch_view_counts(
    session: AsyncSession, target_type: ContentType, ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Batch-load counters for many items of one type (one query, no N+1)."""
    unique_ids = list(dict.fromkeys(ids))
    if not unique_ids:
        return {}
    stmt = select(ViewCounter.target_id, ViewCounter.count).where(
        ViewCounter.target_type == target_type.value,
        ViewCounter.target_id.in_(unique_ids),
    )
    rows = (await session.execute(stmt)).all()
    return {row.target_id: int(row.count) for row in rows}


async def delete_view_counters(
    session: AsyncSession, target_type: ContentType, ids: Iterable[uuid.UUID]
) -> None:
    """Remove counters of deleted content (there is no FK to cascade from)."""
    id_list = list(ids)
    if id_list:
        await session.execute(
            delete(ViewCounter).where(
                ViewCounter.target_type == target_type.value,
                ViewCounter.target_id.in_(id_list),
            )
        )


class EngagementRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def increment_view(self, target_type: ContentType, target_id: uuid.UUID) -> int:
        """Atomically add one view and return the new total.

        A single INSERT ... ON CONFLICT DO UPDATE, so concurrent requests never
        lose increments and no row lock is held across round trips.
        """
        dialect = self.session.get_bind().dialect.name
        insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
        stmt = insert(ViewCounter).values(
            id=uuid.uuid4(),
            target_type=target_type.value,
            target_id=target_id,
            count=1,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ViewCounter.target_type, ViewCounter.target_id],
            set_={"count": ViewCounter.count + 1, "updated_at": func.now()},
        ).returning(ViewCounter.count)
        return int((await self.session.execute(stmt)).scalar_one())

    async def is_public(self, target_type: ContentType, target_id: uuid.UUID) -> bool:
        """Mirror the visibility rules of the public catalog/music endpoints."""
        if target_type == ContentType.PRODUCT:
            condition = select(Product.id).where(
                Product.id == target_id, Product.is_published.is_(True)
            )
        elif target_type == ContentType.MUSIC_TRACK:
            condition = select(MusicTrack.id).where(
                MusicTrack.id == target_id,
                MusicTrack.status == TrackStatus.PUBLISHED.value,
                MusicTrack.assets.any(MusicAsset.kind == AssetKind.AUDIO.value),
            )
        else:
            condition = (
                select(MusicClip.id)
                .join(MusicTrack, MusicTrack.id == MusicClip.track_id)
                .where(
                    MusicClip.id == target_id,
                    MusicClip.is_published.is_(True),
                    MusicTrack.status == TrackStatus.PUBLISHED.value,
                    MusicClip.assets.any(MusicAsset.kind == AssetKind.VIDEO.value),
                )
            )
        return bool(await self.session.scalar(select(exists(condition))))
