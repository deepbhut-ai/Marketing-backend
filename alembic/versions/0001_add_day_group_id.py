"""add day_group_id to posts_post

Revision ID: 0001_day_group
Revises: 
Create Date: 2026-08-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_day_group"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "posts_post",
        sa.Column("day_group_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_posts_post_day_group_id",
        "posts_post",
        ["day_group_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_posts_post_day_group_id", table_name="posts_post")
    op.drop_column("posts_post", "day_group_id")