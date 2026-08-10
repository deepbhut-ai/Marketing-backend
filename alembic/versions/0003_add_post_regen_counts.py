"""add regen counters to posts_post

Revision ID: 0003_post_regens
Revises: 0002_credits
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003_post_regens"
down_revision = "0002_credits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "posts_post",
        sa.Column("caption_regen_count", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "posts_post",
        sa.Column("image_regen_count", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "posts_post",
        sa.Column("video_regen_count", sa.SmallInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("posts_post", "video_regen_count")
    op.drop_column("posts_post", "image_regen_count")
    op.drop_column("posts_post", "caption_regen_count")
