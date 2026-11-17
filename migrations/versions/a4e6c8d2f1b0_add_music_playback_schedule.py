"""add music playback schedule

Revision ID: a4e6c8d2f1b0
Revises: 8c3f2d1a0b9e
Create Date: 2026-08-21 19:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4e6c8d2f1b0"
down_revision: Union[str, Sequence[str], None] = "8c3f2d1a0b9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "music_tracks",
        sa.Column("playback_starts_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("music_tracks", "playback_starts_at")
