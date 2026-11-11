import uuid
from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.catalog.models import Product
from app.domain.localization.models import Translation
from app.domain.music.models import (
    AssetKind,
    MusicAsset,
    MusicClip,
    MusicTrack,
    TrackStatus,
)

from .models import Comment, CommentStatus, ContentType, ViewCounter

TITLE_LANGUAGE_FALLBACK = ("en", "lv", "ru")


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


async def delete_engagement_data(
    session: AsyncSession, target_type: ContentType, ids: Iterable[uuid.UUID]
) -> None:
    """Remove counters and comments of deleted content (no FK to cascade from)."""
    id_list = list(ids)
    if not id_list:
        return
    for model in (ViewCounter, Comment):
        await session.execute(
            delete(model).where(
                model.target_type == target_type.value,
                model.target_id.in_(id_list),
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

    # ---- comments -------------------------------------------------------

    async def add_comment(self, comment: Comment) -> Comment:
        self.session.add(comment)
        await self.session.flush()
        await self.session.refresh(comment)
        return comment

    async def get_comment(self, comment_id: uuid.UUID) -> Comment | None:
        return await self.session.get(Comment, comment_id)

    async def delete_comment(self, comment: Comment) -> None:
        await self.session.delete(comment)

    async def approve_comment(self, comment: Comment) -> Comment:
        comment.status = CommentStatus.APPROVED.value
        comment.approved_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(comment)
        return comment

    async def list_comments(
        self,
        *,
        limit: int,
        offset: int,
        status: CommentStatus | None = None,
        target_type: ContentType | None = None,
        target_id: uuid.UUID | None = None,
    ) -> tuple[list[Comment], int]:
        filters = []
        if status is not None:
            filters.append(Comment.status == status.value)
        if target_type is not None:
            filters.append(Comment.target_type == target_type.value)
        if target_id is not None:
            filters.append(Comment.target_id == target_id)
        total = int(
            await self.session.scalar(
                select(func.count(Comment.id)).where(*filters)
            )
            or 0
        )
        stmt = (
            select(Comment)
            .where(*filters)
            .order_by(Comment.created_at.desc(), Comment.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.scalars(stmt)).all()), total

    async def get_titles(
        self, targets: Iterable[tuple[ContentType, uuid.UUID]], language: str
    ) -> dict[tuple[ContentType, uuid.UUID], str]:
        """Localized titles for many targets: one query per content type.

        Falls back to the other languages, then to the slug (products/tracks).
        """
        by_type: dict[ContentType, set[uuid.UUID]] = {}
        for target_type, target_id in targets:
            by_type.setdefault(target_type, set()).add(target_id)
        languages = [language, *(lang for lang in TITLE_LANGUAGE_FALLBACK if lang != language)]
        titles: dict[tuple[ContentType, uuid.UUID], str] = {}
        for target_type, ids in by_type.items():
            rows = (
                await self.session.execute(
                    select(Translation.entity_id, Translation.lang, Translation.value).where(
                        Translation.entity_type == target_type.value,
                        Translation.entity_id.in_([str(item) for item in ids]),
                        Translation.key == "title",
                        Translation.lang.in_(languages),
                    )
                )
            ).all()
            values: dict[str, dict[str, str]] = {}
            for row in rows:
                if row.value and row.value.strip():
                    values.setdefault(row.entity_id, {})[row.lang] = row.value
            slugs = await self._slugs(target_type, ids)
            for target_id in ids:
                localized = values.get(str(target_id), {})
                titles[(target_type, target_id)] = next(
                    (localized[lang] for lang in languages if lang in localized),
                    slugs.get(target_id, ""),
                )
        return titles

    async def _slugs(
        self, target_type: ContentType, ids: set[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        model = {
            ContentType.PRODUCT: Product,
            ContentType.MUSIC_TRACK: MusicTrack,
        }.get(target_type)
        if model is None:
            return {}
        rows = await self.session.execute(
            select(model.id, model.slug).where(model.id.in_(ids))
        )
        return {row.id: row.slug for row in rows}
