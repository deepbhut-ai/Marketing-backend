"""add brand_brandprofile table

Revision ID: 0005_brand
Revises: 0004_assets
Create Date: 2026-08-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0005_brand"
down_revision = "0004_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brand_brandprofile",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("accounts_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("brand_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("industry", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("website_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("tone", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("target_audience", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("brand_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("brand_keywords", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("primary_colors", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("fonts", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "logo_asset_id",
            sa.Integer(),
            sa.ForeignKey("assets_asset.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("hashtag_pool", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("bio", sa.Text(), nullable=False, server_default=""),
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
    op.create_index(
        "ix_brand_brandprofile_user_id",
        "brand_brandprofile",
        ["user_id"],
    )
    op.create_index(
        "ix_brand_brandprofile_brand_name",
        "brand_brandprofile",
        ["brand_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_brand_brandprofile_brand_name", table_name="brand_brandprofile")
    op.drop_index("ix_brand_brandprofile_user_id", table_name="brand_brandprofile")
    op.drop_table("brand_brandprofile")