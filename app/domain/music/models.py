import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.base import Base


class TrackStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AssetKind(str, enum.Enum):
    AUDIO = "audio"
    COVER = "cover"
    VIDEO = "video"
    POSTER = "poster"


class MusicTrack(Base):
    __tablename__ = "music_tracks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_music_track_status",
        ),
        Index("ix_music_tracks_public_order", "status", "sort_order", "release_date"),
    )

    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=TrackStatus.DRAFT.value, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    clips: Mapped[list["MusicClip"]] = relationship(
        back_populates="track",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="MusicClip.sort_order, MusicClip.created_at",
    )
    assets: Mapped[list["MusicAsset"]] = relationship(
        back_populates="track",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class MusicClip(Base):
    __tablename__ = "music_clips"
    __table_args__ = (
        Index("ix_music_clips_public_order", "is_published", "sort_order"),
    )

    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("music_tracks.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_published: Mapped[bool] = mapped_column(default=False, index=True)
    youtube_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    vimeo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    track: Mapped[MusicTrack] = relationship(back_populates="clips", lazy="selectin")
    assets: Mapped[list["MusicAsset"]] = relationship(
        back_populates="clip",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class MusicAsset(Base):
    __tablename__ = "music_assets"
    __table_args__ = (
        CheckConstraint(
            "((track_id IS NOT NULL AND clip_id IS NULL AND kind IN ('audio', 'cover')) "
            "OR (track_id IS NULL AND clip_id IS NOT NULL AND kind IN ('video', 'poster')))",
            name="ck_music_asset_owner_and_kind",
        ),
        UniqueConstraint("track_id", "kind", name="uq_music_asset_track_kind"),
        UniqueConstraint("clip_id", "kind", name="uq_music_asset_clip_kind"),
    )

    track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("music_tracks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    clip_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("music_clips.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), index=True)
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    codec: Mapped[str | None] = mapped_column(String(100), nullable=True)

    track: Mapped[MusicTrack | None] = relationship(back_populates="assets")
    clip: Mapped[MusicClip | None] = relationship(back_populates="assets")
