"""phase2d_ai_feedback_comparison

Revision ID: d4d7b1f5c436
Revises: d3c6a0e4b327
Create Date: 2026-11-25 23:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4d7b1f5c436"
down_revision: Union[str, Sequence[str], None] = "d3c6a0e4b327"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add cross-modal/routing columns on ai_analyses plus ai_feedback_records & resolution_comparisons."""
    op.add_column("ai_analyses", sa.Column("image_suggested_category", sa.String(length=50), nullable=True))
    op.add_column(
        "ai_analyses",
        sa.Column("cross_modal_mismatch", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("ai_analyses", sa.Column("cross_modal_explanation", sa.Text(), nullable=True))
    op.add_column(
        "ai_analyses",
        sa.Column("routing_tier", sa.String(length=30), nullable=False, server_default="MEDIUM_CONFIDENCE"),
    )
    op.add_column(
        "ai_analyses",
        sa.Column("recommended_action", sa.String(length=50), nullable=False, server_default="REQUIRE_VERIFICATION"),
    )
    op.add_column("ai_analyses", sa.Column("suggested_department_id", sa.String(length=36), nullable=True))

    op.create_table(
        "ai_feedback_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("complaint_id", sa.String(length=36), nullable=False),
        sa.Column("ai_analysis_id", sa.String(length=36), nullable=False),
        sa.Column("reviewer_id", sa.String(length=36), nullable=True),
        sa.Column("original_category", sa.String(length=50), nullable=True),
        sa.Column("corrected_category", sa.String(length=50), nullable=True),
        sa.Column("original_priority", sa.String(length=10), nullable=True),
        sa.Column("corrected_priority", sa.String(length=10), nullable=True),
        sa.Column("original_department_id", sa.String(length=36), nullable=True),
        sa.Column("corrected_department_id", sa.String(length=36), nullable=True),
        sa.Column("original_image_assessment", sa.Text(), nullable=True),
        sa.Column("corrected_image_assessment", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ai_analysis_id"], ["ai_analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_feedback_records_complaint_id"), "ai_feedback_records", ["complaint_id"], unique=False)
    op.create_index(op.f("ix_ai_feedback_records_ai_analysis_id"), "ai_feedback_records", ["ai_analysis_id"], unique=False)
    op.create_index(op.f("ix_ai_feedback_records_reviewer_id"), "ai_feedback_records", ["reviewer_id"], unique=False)
    op.create_index(op.f("ix_ai_feedback_records_created_at"), "ai_feedback_records", ["created_at"], unique=False)

    op.create_table(
        "resolution_comparisons",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("complaint_id", sa.String(length=36), nullable=False),
        sa.Column("before_attachment_id", sa.String(length=36), nullable=False),
        sa.Column("after_attachment_id", sa.String(length=36), nullable=False),
        sa.Column("requested_by_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("changes_detected", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("visual_differences_json", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("uncertainty_notes", sa.Text(), nullable=False),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["after_attachment_id"], ["complaint_attachments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["before_attachment_id"], ["complaint_attachments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_resolution_comparisons_complaint_id"),
        "resolution_comparisons",
        ["complaint_id"],
        unique=False,
    )


def downgrade() -> None:
    """Safely revert Phase 2D AI consistency, feedback, and comparison tables/columns."""
    op.drop_index(op.f("ix_resolution_comparisons_complaint_id"), table_name="resolution_comparisons")
    op.drop_table("resolution_comparisons")

    op.drop_index(op.f("ix_ai_feedback_records_created_at"), table_name="ai_feedback_records")
    op.drop_index(op.f("ix_ai_feedback_records_reviewer_id"), table_name="ai_feedback_records")
    op.drop_index(op.f("ix_ai_feedback_records_ai_analysis_id"), table_name="ai_feedback_records")
    op.drop_index(op.f("ix_ai_feedback_records_complaint_id"), table_name="ai_feedback_records")
    op.drop_table("ai_feedback_records")

    with op.batch_alter_table("ai_analyses") as batch_op:
        batch_op.drop_column("suggested_department_id")
        batch_op.drop_column("recommended_action")
        batch_op.drop_column("routing_tier")
        batch_op.drop_column("cross_modal_explanation")
        batch_op.drop_column("cross_modal_mismatch")
        batch_op.drop_column("image_suggested_category")
