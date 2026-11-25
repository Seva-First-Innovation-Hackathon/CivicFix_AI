import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Float, DateTime, ForeignKey, Index, UniqueConstraint, event
)
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.db.spatial_types import format_geog_point_wkt, wgs84_geography_column_type
from app.models.enums import (
    UserRole, ComplaintCategory, PriorityLevel, ComplaintStatus,
    WorkOrderStatus, DuplicateStatus, NotificationType, AttachmentType, CommentType
)

def generate_uuid() -> str:
    return uuid.uuid4().hex

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    phone_number = Column(String(50), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default=UserRole.CITIZEN.value, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    citizen_profile = relationship("CitizenProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    department_membership = relationship("DepartmentMembership", back_populates="user", uselist=False, cascade="all, delete-orphan")
    crew_profile = relationship("CrewProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    complaints = relationship("Complaint", back_populates="citizen", foreign_keys="Complaint.citizen_id")
    assigned_complaints = relationship("Complaint", back_populates="assigned_crew", foreign_keys="Complaint.assigned_crew_id")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    notification_preferences = relationship("NotificationPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

class CitizenProfile(Base):
    __tablename__ = "citizen_profiles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    preferred_language = Column(String(10), default="en", nullable=False)
    address = Column(String(255), nullable=True)
    emergency_contact = Column(String(50), nullable=True)

    user = relationship("User", back_populates="citizen_profile")

class MunicipalDepartment(Base):
    __tablename__ = "municipal_departments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    jurisdiction = Column(String(255), default="City-wide", nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    members = relationship("DepartmentMembership", back_populates="department")
    crews = relationship("CrewProfile", back_populates="department")
    complaints = relationship("Complaint", back_populates="department")
    work_orders = relationship("WorkOrder", back_populates="department")

class DepartmentMembership(Base):
    __tablename__ = "department_memberships"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    department_id = Column(String(36), ForeignKey("municipal_departments.id", ondelete="CASCADE"), nullable=False)
    designation = Column(String(100), default="Staff Officer", nullable=False)
    jurisdiction = Column(String(255), default="City-wide", nullable=True)
    can_assign = Column(Boolean, default=True, nullable=False)
    can_verify = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="department_membership")
    department = relationship("MunicipalDepartment", back_populates="members")

class CrewProfile(Base):
    __tablename__ = "crew_profiles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    department_id = Column(String(36), ForeignKey("municipal_departments.id", ondelete="CASCADE"), nullable=False)
    vehicle_number = Column(String(50), nullable=True)
    contact_number = Column(String(50), nullable=True)
    active_task_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="crew_profile")
    department = relationship("MunicipalDepartment", back_populates="crews")

class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    reference_number = Column(String(50), unique=True, index=True, nullable=False)
    citizen_id = Column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), default=ComplaintCategory.OTHER.value, nullable=False, index=True)
    subcategory = Column(String(100), nullable=True)
    
    # Location coordinates & PostGIS WGS84 point geography
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    location = Column(wgs84_geography_column_type(), nullable=True)
    address = Column(String(255), nullable=True)
    landmark = Column(String(255), nullable=True)

    # Workflow & Priority
    status = Column(String(50), default=ComplaintStatus.SUBMITTED.value, nullable=False, index=True)
    priority = Column(String(10), default=PriorityLevel.P3.value, nullable=False, index=True)
    department_id = Column(String(36), ForeignKey("municipal_departments.id"), nullable=True, index=True)
    assigned_crew_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    is_disputed = Column(Boolean, default=False, nullable=False)
    sla_deadline = Column(DateTime(timezone=True), nullable=True)

    # Async AI triage execution state
    ai_processing_status = Column(String(30), default="PENDING", server_default="COMPLETED", nullable=False, index=True)
    ai_processing_error = Column(Text, nullable=True)
    ai_processing_attempts = Column(Integer, default=0, server_default="0", nullable=False)
    ai_processing_started_at = Column(DateTime(timezone=True), nullable=True)
    ai_processing_completed_at = Column(DateTime(timezone=True), nullable=True)

    # Explicit status transition reasons
    cancellation_reason = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    investigation_notes = Column(Text, nullable=True)
    clarification_requested = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    citizen = relationship("User", back_populates="complaints", foreign_keys=[citizen_id])
    assigned_crew = relationship("User", back_populates="assigned_complaints", foreign_keys=[assigned_crew_id])
    department = relationship("MunicipalDepartment", back_populates="complaints")
    attachments = relationship("ComplaintAttachment", back_populates="complaint", cascade="all, delete-orphan")
    ai_analysis = relationship("AIAnalysis", back_populates="complaint", uselist=False, cascade="all, delete-orphan")
    status_history = relationship("ComplaintStatusHistory", back_populates="complaint", cascade="all, delete-orphan", order_by="ComplaintStatusHistory.created_at.desc()")
    work_orders = relationship("WorkOrder", back_populates="complaint", cascade="all, delete-orphan")
    resolution_submissions = relationship("ResolutionSubmission", back_populates="complaint", cascade="all, delete-orphan")
    resolution_verifications = relationship("ResolutionVerification", back_populates="complaint", cascade="all, delete-orphan")
    comments = relationship("ComplaintComment", back_populates="complaint", cascade="all, delete-orphan", order_by="ComplaintComment.created_at.asc()")
    ai_feedback_records = relationship("AIFeedback", back_populates="complaint", cascade="all, delete-orphan", order_by="AIFeedback.created_at.desc()")
    resolution_comparisons = relationship("ResolutionComparison", back_populates="complaint", cascade="all, delete-orphan", order_by="ResolutionComparison.created_at.desc()")

    @property
    def is_overdue(self) -> bool:
        if not self.sla_deadline or self.status in ("RESOLVED", "CANCELLED", "REJECTED"):
            return False
        deadline = self.sla_deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > deadline

    @property
    def hours_overdue(self) -> Optional[float]:
        if not self.is_overdue or not self.sla_deadline:
            return None
        deadline = self.sla_deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        delta_sec = (datetime.now(timezone.utc) - deadline).total_seconds()
        return round(max(0.0, delta_sec / 3600.0), 2)

class ComplaintAttachment(Base):
    __tablename__ = "complaint_attachments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    complaint_id = Column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    attachment_type = Column(String(50), default="CITIZEN_ORIGINAL", nullable=False)  # CITIZEN_ORIGINAL, BEFORE_REPAIR, AFTER_REPAIR, RESOLUTION_EVIDENCE, INTERNAL_STAFF_EVIDENCE
    is_internal = Column(Boolean, default=False, nullable=False)  # If True, never exposed to citizen
    description = Column(String(500), nullable=True)
    uploaded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    storage_provider = Column(String(30), default="local", server_default="local", nullable=False, index=True)
    storage_object_key = Column(String(500), nullable=True, index=True)
    sha256_checksum = Column(String(64), nullable=True)
    storage_verification_status = Column(String(30), default="VERIFIED", server_default="PENDING", nullable=False)
    storage_migrated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    complaint = relationship("Complaint", back_populates="attachments")
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_id])

class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    complaint_id = Column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), unique=True, nullable=False)
    provider = Column(String(50), default="mock", nullable=False)
    model_name = Column(String(100), default="civicfix-nlp-v1", nullable=False)
    suggested_category = Column(String(50), nullable=False)
    suggested_subcategory = Column(String(100), nullable=True)
    suggested_priority = Column(String(10), default=PriorityLevel.P3.value, nullable=False)
    confidence_score = Column(Float, default=0.85, nullable=False)
    safety_hazard_detected = Column(Boolean, default=False, nullable=False)
    urgency_level = Column(String(50), default="MEDIUM", nullable=False)
    summary_explanation = Column(Text, nullable=False)
    visual_findings = Column(Text, nullable=True)  # JSON formatted findings
    image_suggested_category = Column(String(50), nullable=True)
    cross_modal_mismatch = Column(Boolean, default=False, server_default="0", nullable=False)
    cross_modal_explanation = Column(Text, nullable=True)
    routing_tier = Column(String(30), default="MEDIUM_CONFIDENCE", server_default="MEDIUM_CONFIDENCE", nullable=False)
    recommended_action = Column(String(50), default="REQUIRE_VERIFICATION", server_default="REQUIRE_VERIFICATION", nullable=False)
    suggested_department_id = Column(String(36), ForeignKey("municipal_departments.id", ondelete="SET NULL"), nullable=True)
    duplicate_checked = Column(Boolean, default=True, nullable=False)
    
    # Audit trail for manual override
    is_overridden = Column(Boolean, default=False, nullable=False)
    overridden_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    override_reason = Column(Text, nullable=True)
    override_timestamp = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    complaint = relationship("Complaint", back_populates="ai_analysis")

class ComplaintStatusHistory(Base):
    __tablename__ = "complaint_status_history"
    __table_args__ = (
        Index("ix_complaint_status_history_complaint_created", "complaint_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    complaint_id = Column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=False)
    changed_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    change_reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    complaint = relationship("Complaint", back_populates="status_history")
    changed_by = relationship("User", foreign_keys=[changed_by_id])

class WorkOrder(Base):
    __tablename__ = "work_orders"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    complaint_id = Column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(String(36), ForeignKey("municipal_departments.id"), nullable=False)
    crew_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    instructions = Column(Text, nullable=False)
    status = Column(String(50), default=WorkOrderStatus.ASSIGNED.value, nullable=False)
    blocker_reason = Column(Text, nullable=True)
    scheduled_date = Column(DateTime(timezone=True), nullable=True)
    completion_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    complaint = relationship("Complaint", back_populates="work_orders")
    department = relationship("MunicipalDepartment", back_populates="work_orders")
    crew = relationship("User", foreign_keys=[crew_id])
    updates = relationship("WorkOrderUpdate", back_populates="work_order", cascade="all, delete-orphan", order_by="WorkOrderUpdate.created_at.desc()")

class WorkOrderUpdate(Base):
    __tablename__ = "work_order_updates"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    work_order_id = Column(String(36), ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    updated_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    note = Column(Text, nullable=False)
    status = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    work_order = relationship("WorkOrder", back_populates="updates")
    updated_by = relationship("User", foreign_keys=[updated_by_id])

class ResolutionSubmission(Base):
    __tablename__ = "resolution_submissions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    complaint_id = Column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True)
    work_order_id = Column(String(36), ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True)
    submitted_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    resolution_notes = Column(Text, nullable=False)
    submitted_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    complaint = relationship("Complaint", back_populates="resolution_submissions")
    submitted_by = relationship("User", foreign_keys=[submitted_by_id])

class ResolutionVerification(Base):
    __tablename__ = "resolution_verifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    complaint_id = Column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True)
    citizen_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    is_satisfied = Column(Boolean, nullable=False)
    feedback_rating = Column(Integer, nullable=True)  # 1 to 5
    feedback_notes = Column(Text, nullable=True)
    reopen_reason = Column(Text, nullable=True)
    verified_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    complaint = relationship("Complaint", back_populates="resolution_verifications")
    citizen = relationship("User", foreign_keys=[citizen_id])

class ComplaintComment(Base):
    __tablename__ = "complaint_comments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    complaint_id = Column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    is_internal = Column(Boolean, default=False, nullable=False)  # If True: hidden from citizens!
    comment_type = Column(String(50), default="STAFF_PUBLIC_NOTE", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    complaint = relationship("Complaint", back_populates="comments")
    author = relationship("User", foreign_keys=[user_id])

class PotentialDuplicate(Base):
    __tablename__ = "potential_duplicates"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    primary_complaint_id = Column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True)
    duplicate_complaint_id = Column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True)
    similarity_score = Column(Float, nullable=False)
    distance_meters = Column(Float, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(50), default=DuplicateStatus.FLAGGED.value, nullable=False)
    reviewed_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    primary_complaint = relationship("Complaint", foreign_keys=[primary_complaint_id])
    duplicate_complaint = relationship("Complaint", foreign_keys=[duplicate_complaint_id])

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(String(50), default=NotificationType.SYSTEM.value, nullable=False)
    complaint_id = Column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    user = relationship("User", back_populates="notifications")

class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    in_app_enabled = Column(Boolean, default=True, nullable=False)
    email_enabled = Column(Boolean, default=True, nullable=False)
    sms_enabled = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="notification_preferences")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    jti = Column(String(64), unique=True, index=True, nullable=False)
    token_hash = Column(String(128), unique=True, index=True, nullable=False)
    family_id = Column(String(64), index=True, nullable=False)
    parent_jti = Column(String(64), nullable=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_reason = Column(String(100), nullable=True)
    replaced_by_jti = Column(String(64), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="refresh_tokens")


class BackgroundJob(Base):
    """Transactional outbox and durable execution record for async AI, email, and SLA monitoring jobs."""
    __tablename__ = "background_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    job_type = Column(String(50), nullable=False, index=True)
    dedup_key = Column(String(160), nullable=True, index=True)
    complaint_id = Column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=True, index=True)
    payload_json = Column(Text, nullable=True)
    status = Column(String(30), default="PENDING_DISPATCH", nullable=False, index=True)
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    next_run_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    redis_job_id = Column(String(120), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class SLABreachEvent(Base):
    """Deduplicated record of SLA deadline breaches for accountability, notifications, and analytics."""
    __tablename__ = "sla_breach_events"
    __table_args__ = (
        UniqueConstraint("complaint_id", "sla_deadline", name="uq_sla_breach_complaint_deadline"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    complaint_id = Column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True)
    priority = Column(String(10), nullable=False)
    sla_deadline = Column(DateTime(timezone=True), nullable=False)
    detected_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    hours_overdue = Column(Float, nullable=False)
    notification_sent = Column(Boolean, default=False, nullable=False)
    notified_user_count = Column(Integer, default=0, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    complaint = relationship("Complaint")


class AIFeedback(Base):
    """Structured staff correction log capturing AI overrides for operational audit and evaluation."""
    __tablename__ = "ai_feedback_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    complaint_id = Column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True)
    ai_analysis_id = Column(String(36), ForeignKey("ai_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    original_category = Column(String(50), nullable=True)
    corrected_category = Column(String(50), nullable=True)
    original_priority = Column(String(10), nullable=True)
    corrected_priority = Column(String(10), nullable=True)
    original_department_id = Column(String(36), nullable=True)
    corrected_department_id = Column(String(36), nullable=True)
    original_image_assessment = Column(Text, nullable=True)
    corrected_image_assessment = Column(Text, nullable=True)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    complaint = relationship("Complaint", back_populates="ai_feedback_records")
    reviewer = relationship("User", foreign_keys=[reviewer_id])


class ResolutionComparison(Base):
    """Advisory AI visual comparison between citizen before-repair and crew after-repair evidence."""
    __tablename__ = "resolution_comparisons"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    complaint_id = Column(String(36), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True)
    before_attachment_id = Column(String(36), ForeignKey("complaint_attachments.id", ondelete="CASCADE"), nullable=False)
    after_attachment_id = Column(String(36), ForeignKey("complaint_attachments.id", ondelete="CASCADE"), nullable=False)
    requested_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    provider = Column(String(50), nullable=False)
    model_name = Column(String(100), nullable=False)
    changes_detected = Column(Boolean, default=True, nullable=False)
    visual_differences_json = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    uncertainty_notes = Column(Text, nullable=False)
    requires_human_review = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    complaint = relationship("Complaint", back_populates="resolution_comparisons")


def _sync_complaint_location(_mapper, _connection, target: Complaint) -> None:
    """Keep Complaint.location synchronized with validated latitude and longitude."""
    target.location = format_geog_point_wkt(target.latitude, target.longitude)


event.listen(Complaint, "before_insert", _sync_complaint_location)
event.listen(Complaint, "before_update", _sync_complaint_location)

