"""phase2a_storage_metadata

Revision ID: d1a4e8c2f109
Revises: b4e2d9c1f8a3
Create Date: 2026-11-25 22:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1a4e8c2f109"
down_revision: Union[str, Sequence[str], None] = "b4e2d9c1f8a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add durable cloud storage metadata columns to complaint_attachments."""
    op.add_column(
        "complaint_attachments",
        sa.Column("storage_provider", sa.String(length=30), nullable=False, server_default="local"),
    )
    op.add_column(
        "complaint_attachments",
        sa.Column("storage_object_key", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "complaint_attachments",
        sa.Column("sha256_checksum", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "complaint_attachments",
        sa.Column("storage_verification_status", sa.String(length=30), nullable=False, server_default="PENDING"),
    )
    op.add_column(
        "complaint_attachments",
        sa.Column("storage_migrated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_complaint_attachments_storage_provider"),
        "complaint_attachments",
        ["storage_provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_complaint_attachments_storage_object_key"),
        "complaint_attachments",
        ["storage_object_key"],
        unique=False,
    )


def downgrade() -> None:
    """Revert Phase 2A cloud storage metadata columns cleanly."""
    op.drop_index(op.f("ix_complaint_attachments_storage_object_key"), table_name="complaint_attachments")
    op.drop_index(op.f("ix_complaint_attachments_storage_provider"), table_name="complaint_attachments")
    with op.batch_alter_table("complaint_attachments") as batch_op:
        batch_op.drop_column("storage_migrated_at")
        batch_op.drop_column("storage_verification_status")
        batch_op.drop_column("sha256_checksum")
        batch_op.drop_column("storage_object_key")
        batch_op.drop_column("storage_provider")
