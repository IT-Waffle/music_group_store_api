import enum
import uuid

from sqlalchemy import BigInteger, CheckConstraint, String, UniqueConstraint, Uuid
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
