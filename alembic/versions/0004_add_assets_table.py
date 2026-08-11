"""add assets_asset table

Revision ID: 0004_assets
Revises: 0003_post_regens
Create Date: 2026-08-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0004_assets"
down_revision = "0003_post_regens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets_asset",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("accounts_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        # Relative path under MEDIA_DIR for uploaded/generated files.
        sa.Column("file", sa.String(length=500), nullable=True),
        # External URL when the binary is hosted elsewhere.
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=1024), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="uploaded"),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_assets_asset_user_id", "assets_asset", ["user_id"])
    op.create_index("ix_assets_asset_asset_type", "assets_asset", ["asset_type"])
    op.create_index("ix_assets_asset_external_id", "assets_asset", ["external_id"])
    op.create_index("ix_assets_asset_created_at", "assets_asset", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_assets_asset_created_at", table_name="assets_asset")
    op.drop_index("ix_assets_asset_external_id", table_name="assets_asset")
    op.drop_index("ix_assets_asset_asset_type", table_name="assets_asset")
    op.drop_index("ix_assets_asset_user_id", table_name="assets_asset")
    op.drop_table("assets_asset")
