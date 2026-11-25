"""phase2c_background_jobs_sla

Revision ID: d3c6a0e4b327
Revises: d2b5f9d3a218
Create Date: 2026-11-25 22:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d3c6a0e4b327"
down_revision: Union[str, Sequence[str], None] = "d2b5f9d3a218"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create transactional outbox table background_jobs and sla_breach_events table."""
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("dedup_key", sa.String(length=160), nullable=True),
        sa.Column("complaint_id", sa.String(length=36), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING_DISPATCH"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("redis_job_id", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_background_jobs_job_type"), "background_jobs", ["job_type"], unique=False)
    op.create_index(op.f("ix_background_jobs_dedup_key"), "background_jobs", ["dedup_key"], unique=False)
    op.create_index(op.f("ix_background_jobs_complaint_id"), "background_jobs", ["complaint_id"], unique=False)
    op.create_index(op.f("ix_background_jobs_status"), "background_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_background_jobs_next_run_at"), "background_jobs", ["next_run_at"], unique=False)

    op.create_table(
        "sla_breach_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("complaint_id", sa.String(length=36), nullable=False),
        sa.Column("priority", sa.String(length=10), nullable=False),
        sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hours_overdue", sa.Float(), nullable=False),
        sa.Column("notification_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notified_user_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("complaint_id", "sla_deadline", name="uq_sla_breach_complaint_deadline"),
    )
    op.create_index(op.f("ix_sla_breach_events_complaint_id"), "sla_breach_events", ["complaint_id"], unique=False)
    op.create_index(op.f("ix_sla_breach_events_detected_at"), "sla_breach_events", ["detected_at"], unique=False)


def downgrade() -> None:
    """Safely revert Phase 2C background_jobs and sla_breach_events tables."""
    op.drop_index(op.f("ix_sla_breach_events_detected_at"), table_name="sla_breach_events")
    op.drop_index(op.f("ix_sla_breach_events_complaint_id"), table_name="sla_breach_events")
    op.drop_table("sla_breach_events")

    op.drop_index(op.f("ix_background_jobs_next_run_at"), table_name="background_jobs")
    op.drop_index(op.f("ix_background_jobs_status"), table_name="background_jobs")
    op.drop_index(op.f("ix_background_jobs_complaint_id"), table_name="background_jobs")
    op.drop_index(op.f("ix_background_jobs_dedup_key"), table_name="background_jobs")
    op.drop_index(op.f("ix_background_jobs_job_type"), table_name="background_jobs")
    op.drop_table("background_jobs")
