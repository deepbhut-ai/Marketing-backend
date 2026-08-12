"""add posts_postlog table

Revision ID: 0006_postlog
Revises: 0005_brand
Create Date: 2026-08-12

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0006_postlog"
down_revision = "0005_brand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "posts_postlog",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("accounts_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "post_id",
            sa.Integer(),
            sa.ForeignKey("posts_post.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=True),
        sa.Column("day_group_id", sa.String(length=36), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_posts_postlog_user_id",
        "posts_postlog",
        ["user_id"],
    )
    op.create_index(
        "ix_posts_postlog_post_id",
        "posts_postlog",
        ["post_id"],
    )
    op.create_index(
        "ix_posts_postlog_action",
        "posts_postlog",
        ["action"],
    )
    op.create_index(
        "ix_posts_postlog_day_group_id",
        "posts_postlog",
        ["day_group_id"],
    )
    op.create_index(
        "ix_posts_postlog_created_at",
        "posts_postlog",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_posts_postlog_created_at", table_name="posts_postlog")
    op.drop_index("ix_posts_postlog_day_group_id", table_name="posts_postlog")
    op.drop_index("ix_posts_postlog_action", table_name="posts_postlog")
    op.drop_index("ix_posts_postlog_post_id", table_name="posts_postlog")
    op.drop_index("ix_posts_postlog_user_id", table_name="posts_postlog")
    op.drop_table("posts_postlog")