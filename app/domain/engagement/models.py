import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.base import Base


class ContentType(str, enum.Enum):
    """Public content entities that can be viewed (and later commented on)."""

    PRODUCT = "product"
    MUSIC_TRACK = "music_track"
    MUSIC_CLIP = "music_clip"


CONTENT_TYPE_VALUES = ", ".join(f"'{item.value}'" for item in ContentType)


class ViewCounter(Base):
    """Non-unique view counter, one row per content item.

    Kept outside the content tables so that frequent increments never touch
    products/tracks/clips rows (and their updated_at).
    """

    __tablename__ = "view_counters"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", name="uq_view_counters_target"),
        CheckConstraint(
            f"target_type IN ({CONTENT_TYPE_VALUES})",
            name="ck_view_counters_target_type",
        ),
    )

    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")


class CommentStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"


class Comment(Base):
    """Visitor comment. Public only after approval; rejected ones are deleted."""

    __tablename__ = "comments"
    __table_args__ = (
        CheckConstraint(
            f"target_type IN ({CONTENT_TYPE_VALUES})",
            name="ck_comments_target_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved')", name="ck_comments_status"
        ),
        # Public thread of one item: approved, newest first.
        Index(
            "ix_comments_target_status_created",
            "target_type",
            "target_id",
            "status",
            "created_at",
        ),
        # Moderation queue.
        Index("ix_comments_status_created", "status", "created_at"),
    )

    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    author_name: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20),
        default=CommentStatus.PENDING.value,
        server_default=CommentStatus.PENDING.value,
    )
    # Timezone-aware (unlike the global Base) because the comment date is shown
    # to visitors and must be unambiguous.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set when the owner's email notification was delivered to the provider.
    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
