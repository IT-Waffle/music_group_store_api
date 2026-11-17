"""add music track is_playable column

Revision ID: 8c3f2d1a0b9e
Revises: 5fe558a4ee4f
Create Date: 2026-08-21 19:20:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "8c3f2d1a0b9e"
down_revision: Union[str, Sequence[str], None] = "5fe558a4ee4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE music_tracks "
        "ADD COLUMN IF NOT EXISTS is_playable BOOLEAN NOT NULL DEFAULT true"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE music_tracks DROP COLUMN IF EXISTS is_playable")
