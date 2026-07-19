"""add music domain

Revision ID: 9a7d3c2e1f40
Revises: 73316b48f694
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a7d3c2e1f40"
down_revision: str | Sequence[str] | None = "73316b48f694"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "music_tracks",
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_music_track_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_music_tracks_slug"), "music_tracks", ["slug"])
    op.create_index(op.f("ix_music_tracks_status"), "music_tracks", ["status"])
    op.create_index(
        "ix_music_tracks_public_order",
        "music_tracks",
        ["status", "sort_order", "release_date"],
    )

    op.create_table(
        "music_clips",
        sa.Column("track_id", sa.Uuid(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("youtube_url", sa.String(length=2048), nullable=True),
        sa.Column("vimeo_url", sa.String(length=2048), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["track_id"], ["music_tracks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_music_clips_track_id"), "music_clips", ["track_id"])
    op.create_index(
        op.f("ix_music_clips_is_published"), "music_clips", ["is_published"]
    )
    op.create_index(
        "ix_music_clips_public_order",
        "music_clips",
        ["is_published", "sort_order"],
    )

    op.create_table(
        "music_assets",
        sa.Column("track_id", sa.Uuid(), nullable=True),
        sa.Column("clip_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("codec", sa.String(length=100), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "((track_id IS NOT NULL AND clip_id IS NULL AND kind IN ('audio', 'cover')) "
            "OR (track_id IS NULL AND clip_id IS NOT NULL AND kind IN ('video', 'poster')))",
            name="ck_music_asset_owner_and_kind",
        ),
        sa.ForeignKeyConstraint(["clip_id"], ["music_clips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["track_id"], ["music_tracks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clip_id", "kind", name="uq_music_asset_clip_kind"),
        sa.UniqueConstraint("storage_key"),
        sa.UniqueConstraint("track_id", "kind", name="uq_music_asset_track_kind"),
    )
    op.create_index(op.f("ix_music_assets_clip_id"), "music_assets", ["clip_id"])
    op.create_index(op.f("ix_music_assets_kind"), "music_assets", ["kind"])
    op.create_index(op.f("ix_music_assets_track_id"), "music_assets", ["track_id"])


def downgrade() -> None:
    op.execute(
        "DELETE FROM translations WHERE entity_type IN ('music_track', 'music_clip')"
    )
    op.drop_index(op.f("ix_music_assets_track_id"), table_name="music_assets")
    op.drop_index(op.f("ix_music_assets_kind"), table_name="music_assets")
    op.drop_index(op.f("ix_music_assets_clip_id"), table_name="music_assets")
    op.drop_table("music_assets")
    op.drop_index("ix_music_clips_public_order", table_name="music_clips")
    op.drop_index(op.f("ix_music_clips_is_published"), table_name="music_clips")
    op.drop_index(op.f("ix_music_clips_track_id"), table_name="music_clips")
    op.drop_table("music_clips")
    op.drop_index("ix_music_tracks_public_order", table_name="music_tracks")
    op.drop_index(op.f("ix_music_tracks_status"), table_name="music_tracks")
    op.drop_index(op.f("ix_music_tracks_slug"), table_name="music_tracks")
    op.drop_table("music_tracks")
