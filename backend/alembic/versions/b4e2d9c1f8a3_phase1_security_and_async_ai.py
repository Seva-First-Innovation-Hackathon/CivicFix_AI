"""phase1_security_and_async_ai

Revision ID: b4e2d9c1f8a3
Revises: adca60ea77e0
Create Date: 2026-11-25 22:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4e2d9c1f8a3"
down_revision: Union[str, Sequence[str], None] = "adca60ea77e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema cleanly with additive tables, columns, and indexes."""
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=64), nullable=False),
        sa.Column("parent_jti", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=100), nullable=True),
        sa.Column("replaced_by_jti", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_refresh_tokens_jti"), "refresh_tokens", ["jti"], unique=True)
    op.create_index(op.f("ix_refresh_tokens_token_hash"), "refresh_tokens", ["token_hash"], unique=True)
    op.create_index(op.f("ix_refresh_tokens_family_id"), "refresh_tokens", ["family_id"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_is_revoked"), "refresh_tokens", ["is_revoked"], unique=False)

    op.add_column(
        "complaints",
        sa.Column("ai_processing_status", sa.String(length=30), nullable=False, server_default="COMPLETED"),
    )
    op.add_column("complaints", sa.Column("ai_processing_error", sa.Text(), nullable=True))
    op.add_column(
        "complaints",
        sa.Column("ai_processing_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("complaints", sa.Column("ai_processing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("complaints", sa.Column("ai_processing_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_complaints_ai_processing_status"), "complaints", ["ai_processing_status"], unique=False)

    op.create_index(
        "ix_complaint_status_history_complaint_created",
        "complaint_status_history",
        ["complaint_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Safely revert Phase 1 schema additions."""
    op.drop_index("ix_complaint_status_history_complaint_created", table_name="complaint_status_history")

    op.drop_index(op.f("ix_complaints_ai_processing_status"), table_name="complaints")
    with op.batch_alter_table("complaints") as batch_op:
        batch_op.drop_column("ai_processing_completed_at")
        batch_op.drop_column("ai_processing_started_at")
        batch_op.drop_column("ai_processing_attempts")
        batch_op.drop_column("ai_processing_error")
        batch_op.drop_column("ai_processing_status")

    op.drop_index(op.f("ix_refresh_tokens_is_revoked"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_family_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_token_hash"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_jti"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
