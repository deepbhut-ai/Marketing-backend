"""add credit rate + credit log tables

Revision ID: 0002_credits
Revises: 0001_day_group
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_credits"
down_revision = "0001_day_group"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── credits_creditrate ──────────────────────────────────────────
    op.create_table(
        "credits_creditrate",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("action_key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("credits", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        "ix_credits_creditrate_action_key",
        "credits_creditrate",
        ["action_key"],
        unique=True,
    )

    # ── credits_creditlog ───────────────────────────────────────────
    op.create_table(
        "credits_creditlog",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("accounts_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action_key", sa.String(length=64), nullable=False),
        sa.Column("credits_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reference_type", sa.String(length=64), nullable=True),
        sa.Column("reference_id", sa.Integer(), nullable=True),
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
        "ix_credits_creditlog_user_id",
        "credits_creditlog",
        ["user_id"],
    )
    op.create_index(
        "ix_credits_creditlog_action_key",
        "credits_creditlog",
        ["action_key"],
    )
    op.create_index(
        "ix_credits_creditlog_created_at",
        "credits_creditlog",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_credits_creditlog_created_at", table_name="credits_creditlog")
    op.drop_index("ix_credits_creditlog_action_key", table_name="credits_creditlog")
    op.drop_index("ix_credits_creditlog_user_id", table_name="credits_creditlog")
    op.drop_table("credits_creditlog")

    op.drop_index("ix_credits_creditrate_action_key", table_name="credits_creditrate")
    op.drop_table("credits_creditrate")
