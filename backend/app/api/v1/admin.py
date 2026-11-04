import io
import csv
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.db.session import get_db
from app.api.deps import (
    get_current_user, require_municipal_staff, require_government_admin,
    require_any_staff, enforce_single_admin_invariant
)
from app.models.entities import (
    User, MunicipalDepartment, DepartmentMembership, CrewProfile,
    Complaint, ComplaintAttachment, AIAnalysis, ComplaintStatusHistory,
    WorkOrder, WorkOrderUpdate, ResolutionSubmission, PotentialDuplicate,
    AuditLog, SystemSetting, Notification, ComplaintComment, ResolutionVerification
)
from app.models.enums import (
    UserRole, ComplaintStatus, PriorityLevel, WorkOrderStatus,
    DuplicateStatus, NotificationType, CommentType
)
from app.schemas.user import StaffCreateRequest, UserResponse, UserUpdate
from app.schemas.complaint import (
    ComplaintResponse, ComplaintListResponse, ComplaintStatusUpdateRequest,
    ComplaintAssignmentRequest, AIOverrideRequest, ResolutionSubmitRequest,
    ComplaintVerifyRequest, ComplaintRejectRequest, ComplaintFlagInvestigationRequest,
    ReviewEvidenceRequest, ComplaintCommentCreateRequest, ComplaintCommentResponse,
    ComplaintClarificationRequest
)
from app.schemas.department import DepartmentCreate, DepartmentUpdate, DepartmentResponse
from app.schemas.work_order import (
    WorkOrderCreate, WorkOrderStatusUpdate, WorkOrderResponse,
    WorkOrderSubmitEvidenceRequest
)
from app.schemas.duplicate import PotentialDuplicateResponse, DuplicateReviewRequest
from app.schemas.analytics import AnalyticsOverview, KeyMetrics, CategoryCount, PriorityCount, DepartmentCount, TrendDataPoint
from app.schemas.audit import AuditLogResponse, SystemSettingResponse, SystemSettingUpdate
from app.core.security import get_password_hash
from app.services.audit import log_audit
from app.services.notifications.service import send_notification
from app.services.email.service import email_service
from app.services.complaints.lifecycle import execute_transition

router = APIRouter(prefix="/admin", tags=["Municipal Administration"])

# ----------------- DASHBOARD METRICS -----------------

@router.get("/dashboard", response_model=AnalyticsOverview)
def get_dashboard_metrics(
    current_user: User = Depends(require_any_staff),
    db: Session = Depends(get_db)
):
    """
    Computes real-time municipal dashboard metrics directly from the database.
    """
    now = datetime.now(timezone.utc)
    total = db.query(Complaint).count()
    active = db.query(Complaint).filter(Complaint.status.notin_(["RESOLVED", "CANCELLED"])).count()
    pending_review = db.query(Complaint).filter(Complaint.status == "UNDER_REVIEW").count()
    in_progress = db.query(Complaint).filter(Complaint.status == "IN_PROGRESS").count()
    awaiting_conf = db.query(Complaint).filter(Complaint.status == "AWAITING_CITIZEN_CONFIRMATION").count()
    resolved = db.query(Complaint).filter(Complaint.status == "RESOLVED").count()
    reopened = db.query(Complaint).filter(Complaint.status == "REOPENED").count()
    high_prio = db.query(Complaint).filter(
        Complaint.priority.in_(["P1", "P2"]),
        Complaint.status.notin_(["RESOLVED", "CANCELLED"])
    ).count()
    overdue = db.query(Complaint).filter(
        Complaint.sla_deadline < now,
        Complaint.status.notin_(["RESOLVED", "CANCELLED"])
    ).count()

    # Real dynamic computation from database
    resolved_complaints = db.query(Complaint).filter(Complaint.status == "RESOLVED").all()
    if resolved_complaints:
        total_seconds = sum(
            (c.updated_at - c.created_at).total_seconds()
            for c in resolved_complaints
            if c.updated_at and c.created_at
        )
        avg_res_hours = round(total_seconds / (len(resolved_complaints) * 3600.0), 1)
    else:
        avg_res_hours = 0.0

    # Satisfaction rate computed from resolution verifications
    total_verifications = db.query(ResolutionVerification).count()
    if total_verifications > 0:
        satisfied_count = db.query(ResolutionVerification).filter(ResolutionVerification.is_satisfied == True).count()
        satisfaction_rate = round((satisfied_count / total_verifications) * 100.0, 1)
    else:
        satisfaction_rate = 100.0

    metrics = KeyMetrics(
        total_complaints=total,
        active_complaints=active,
        pending_review=pending_review,
        in_progress=in_progress,
        awaiting_citizen_confirmation=awaiting_conf,
        resolved_complaints=resolved,
        reopened_complaints=reopened,
        high_priority_unresolved=high_prio,
        overdue_complaints=overdue,
        average_resolution_hours=avg_res_hours,
        citizen_satisfaction_rate=satisfaction_rate
    )

    # By Category
    cat_counts = db.query(Complaint.category, func.count(Complaint.id)).group_by(Complaint.category).all()
    by_category = [
        CategoryCount(
            category=cat,
            count=cnt,
            percentage=round((cnt / total * 100.0), 1) if total > 0 else 0.0
        )
        for cat, cnt in cat_counts
    ]

    # By Priority
    prio_counts = db.query(Complaint.priority, func.count(Complaint.id)).group_by(Complaint.priority).all()
    by_priority = [
        PriorityCount(
            priority=prio,
            count=cnt,
            percentage=round((cnt / total * 100.0), 1) if total > 0 else 0.0
        )
        for prio, cnt in prio_counts
    ]

    # By Department
    depts = db.query(MunicipalDepartment).all()
    by_department = []
    for d in depts:
        d_total = db.query(Complaint).filter(Complaint.department_id == d.id).count()
        d_res = db.query(Complaint).filter(Complaint.department_id == d.id, Complaint.status == "RESOLVED").count()
        by_department.append(DepartmentCount(
            department_name=d.name,
            count=d_total,
            resolved_count=d_res
        ))

    # Trends (past 7 days)
    trends = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = day.replace(hour=23, minute=59, second=59, microsecond=999999)
        sub_cnt = db.query(Complaint).filter(Complaint.created_at >= start, Complaint.created_at <= end).count()
        res_cnt = db.query(Complaint).filter(Complaint.status == "RESOLVED", Complaint.updated_at >= start, Complaint.updated_at <= end).count()
        trends.append(TrendDataPoint(date=day_str, submitted=sub_cnt, resolved=res_cnt))

    return AnalyticsOverview(
        metrics=metrics,
        by_category=by_category,
        by_priority=by_priority,
        by_department=by_department,
        trends=trends
    )

# ----------------- COMPLAINT MANAGEMENT -----------------

@router.get("/complaints", response_model=ComplaintListResponse)
def list_all_complaints(
    page: int = 1,
    page_size: int = 20,
    category: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    department_id: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(require_any_staff),
    db: Session = Depends(get_db)
):
    """
    Filterable and paginated complaint register for municipal staff.
    Enforces strict role and department scoping:
    - Field Crew: Only views complaints assigned directly to them.
    - Municipal Member: Restricted to their department and unassigned queue.
    - Government Admin: Global municipality-wide visibility.
    """
    query = db.query(Complaint)

    # Role and department scoping boundary
    if current_user.role == UserRole.FIELD_CREW.value:
        query = query.filter(Complaint.assigned_crew_id == current_user.id)
    elif current_user.role == UserRole.MUNICIPAL_MEMBER.value:
        if current_user.department_membership:
            user_dept_id = current_user.department_membership.department_id
            if department_id and department_id != user_dept_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You cannot view complaints from other municipal departments."
                )
            query = query.filter(or_(Complaint.department_id == user_dept_id, Complaint.department_id == None))
        else:
            query = query.filter(Complaint.department_id == None)
    elif department_id:
        query = query.filter(Complaint.department_id == department_id)

    if category:
        query = query.filter(Complaint.category == category)
    if status:
        query = query.filter(Complaint.status == status)
    if priority:
        query = query.filter(Complaint.priority == priority)
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                Complaint.reference_number.ilike(search_filter),
                Complaint.title.ilike(search_filter),
                Complaint.description.ilike(search_filter),
                Complaint.address.ilike(search_filter)
            )
        )

    total = query.count()
    complaints = (
        query.order_by(Complaint.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ComplaintListResponse(
        total=total,
        page=page,
        page_size=page_size,
        complaints=complaints
    )

@router.get("/complaints/{complaint_id}", response_model=ComplaintResponse)
def get_complaint_admin(
    complaint_id: str,
    current_user: User = Depends(require_any_staff),
    db: Session = Depends(get_db)
):
    """Retrieve complete complaint record with AI analysis and attachments."""
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    # Scope checks
    if current_user.role == UserRole.FIELD_CREW.value:
        has_wo = db.query(WorkOrder).filter(WorkOrder.complaint_id == complaint.id, WorkOrder.crew_id == current_user.id).first()
        if complaint.assigned_crew_id != current_user.id and not has_wo:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Complaint is not assigned to your crew"
            )

    elif current_user.role == UserRole.MUNICIPAL_MEMBER.value:
        if complaint.department_id and current_user.department_membership:
            if current_user.department_membership.department_id != complaint.department_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Complaint belongs to a different department"
                )

    return complaint

@router.patch("/complaints/{complaint_id}", response_model=ComplaintResponse)
def update_complaint_status(
    complaint_id: str,
    data: ComplaintStatusUpdateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_municipal_staff),
    db: Session = Depends(get_db)
):
    """
    Explicit status transition validated via server-side state machine.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    complaint = execute_transition(
        db=db,
        complaint=complaint,
        target_status=data.status.value,
        user=current_user,
        reason=data.reason or "Administrative status transition",
        notes=data.notes,
        background_tasks=background_tasks
    )
    return complaint

@router.post("/complaints/{complaint_id}/verify", response_model=ComplaintResponse)
def verify_complaint(
    complaint_id: str,
    data: ComplaintVerifyRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_municipal_staff),
    db: Session = Depends(get_db)
):
    """
    Municipal staff verifies complaint validity and sets confirmed priority (P1-P4).
    Transitions complaint from UNDER_REVIEW to VERIFIED.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    complaint.priority = data.priority.value
    complaint = execute_transition(
        db=db,
        complaint=complaint,
        target_status=ComplaintStatus.VERIFIED.value,
        user=current_user,
        reason=f"Verified complaint and confirmed priority {data.priority.value}",
        notes=data.verification_notes,
        background_tasks=background_tasks
    )
    return complaint

@router.post("/complaints/{complaint_id}/request-info", response_model=ComplaintResponse)
def request_more_information(
    complaint_id: str,
    data: ComplaintClarificationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_municipal_staff),
    db: Session = Depends(get_db)
):
    """
    Staff requests additional details or clearer photos from citizen.
    Transitions complaint to AWAITING_CITIZEN_INFORMATION.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    # Add information request comment
    comment = ComplaintComment(
        complaint_id=complaint.id,
        user_id=current_user.id,
        content=data.information,
        is_internal=False,
        comment_type=CommentType.INFO_REQUEST.value
    )
    db.add(comment)

    complaint = execute_transition(
        db=db,
        complaint=complaint,
        target_status=ComplaintStatus.AWAITING_CITIZEN_INFORMATION.value,
        user=current_user,
        reason=data.information,
        background_tasks=background_tasks
    )
    return complaint

@router.post("/complaints/{complaint_id}/reject", response_model=ComplaintResponse)
def reject_complaint(
    complaint_id: str,
    data: ComplaintRejectRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_municipal_staff),
    db: Session = Depends(get_db)
):
    """
    Staff rejects an invalid, duplicate, or out-of-jurisdiction complaint with documented reason.
    Transitions complaint to REJECTED.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    complaint = execute_transition(
        db=db,
        complaint=complaint,
        target_status=ComplaintStatus.REJECTED.value,
        user=current_user,
        reason=data.reason,
        background_tasks=background_tasks
    )
    return complaint

@router.post("/complaints/{complaint_id}/flag-investigation", response_model=ComplaintResponse)
def flag_complaint_for_investigation(
    complaint_id: str,
    data: ComplaintFlagInvestigationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_municipal_staff),
    db: Session = Depends(get_db)
):
    """
    Staff flags suspicious, fraudulent, or hazardous issue for municipal investigation.
    Transitions complaint to FLAGGED_FOR_INVESTIGATION.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    complaint = execute_transition(
        db=db,
        complaint=complaint,
        target_status=ComplaintStatus.FLAGGED_FOR_INVESTIGATION.value,
        user=current_user,
        reason=data.reason,
        background_tasks=background_tasks
    )
    return complaint

@router.post("/complaints/{complaint_id}/review-evidence", response_model=ComplaintResponse)
def review_completion_evidence(
    complaint_id: str,
    data: ReviewEvidenceRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_municipal_staff),
    db: Session = Depends(get_db)
):
    """
    Municipal Staff reviews field crew repair evidence:
    - If approved: moves to AWAITING_CITIZEN_CONFIRMATION for citizen inspection.
    - If rejected: returns to IN_PROGRESS for rework.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    target_status = (
        ComplaintStatus.AWAITING_CITIZEN_CONFIRMATION.value
        if data.is_approved
        else ComplaintStatus.IN_PROGRESS.value
    )
    action_note = "Staff approved completion evidence" if data.is_approved else "Evidence insufficient, returned for further remediation"

    complaint = execute_transition(
        db=db,
        complaint=complaint,
        target_status=target_status,
        user=current_user,
        reason=action_note,
        notes=data.notes,
        background_tasks=background_tasks
    )
    return complaint

@router.post("/complaints/{complaint_id}/internal-note", response_model=ComplaintCommentResponse)
def add_internal_staff_note(
    complaint_id: str,
    data: ComplaintCommentCreateRequest,
    current_user: User = Depends(require_municipal_staff),
    db: Session = Depends(get_db)
):
    """
    Municipal staff adds an internal investigation note, hidden from citizens.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    comment = ComplaintComment(
        complaint_id=complaint.id,
        user_id=current_user.id,
        content=data.content,
        is_internal=True,  # strictly internal!
        comment_type=CommentType.STAFF_INTERNAL_NOTE.value
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    return ComplaintCommentResponse(
        id=comment.id,
        complaint_id=comment.complaint_id,
        user_id=comment.user_id,
        user_name=current_user.full_name,
        user_role=current_user.role,
        content=comment.content,
        is_internal=True,
        comment_type=comment.comment_type,
        created_at=comment.created_at
    )

@router.post("/complaints/{complaint_id}/assign", response_model=ComplaintResponse)
def assign_complaint(
    complaint_id: str,
    data: ComplaintAssignmentRequest,
    current_user: User = Depends(require_municipal_staff),
    db: Session = Depends(get_db)
):
    """Assigns complaint to a municipal department and sets confirmed priority."""
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    dept = db.query(MunicipalDepartment).filter(MunicipalDepartment.id == data.department_id).first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    old_status = complaint.status
    complaint.department_id = dept.id
    if data.priority:
        complaint.priority = data.priority.value
    complaint.status = ComplaintStatus.ASSIGNED.value

    history = ComplaintStatusHistory(
        complaint_id=complaint.id,
        from_status=old_status,
        to_status=ComplaintStatus.ASSIGNED.value,
        changed_by_id=current_user.id,
        change_reason=f"Assigned to {dept.name}",
        notes=data.notes
    )
    db.add(history)

    send_notification(
        db=db,
        user_id=complaint.citizen_id,
        title="Assigned to Department",
        message=f"Your complaint #{complaint.reference_number} has been routed to {dept.name}.",
        notification_type=NotificationType.DEPARTMENT_ASSIGNED.value,
        complaint_id=complaint.id
    )

    log_audit(
        db=db,
        action="COMPLAINT_ASSIGNMENT",
        entity_type="COMPLAINT",
        entity_id=complaint.id,
        user_id=current_user.id,
        details={"department_id": dept.id, "priority": complaint.priority}
    )

    db.commit()
    db.refresh(complaint)
    return complaint

@router.post("/complaints/{complaint_id}/review-ai", response_model=ComplaintResponse)
def override_ai_assessment(
    complaint_id: str,
    data: AIOverrideRequest,
    current_user: User = Depends(require_municipal_staff),
    db: Session = Depends(get_db)
):
    """
    Municipal staff reviews and overrides AI triage recommendation.
    Enforces recorded justification for accountability.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    if not complaint.ai_analysis:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No AI assessment exists for this complaint")

    ai_record = complaint.ai_analysis
    ai_record.is_overridden = True
    ai_record.overridden_by_id = current_user.id
    ai_record.override_reason = data.override_reason
    ai_record.override_timestamp = datetime.now(timezone.utc)

    if data.category:
        complaint.category = data.category.value
    if data.priority:
        complaint.priority = data.priority.value

    log_audit(
        db=db,
        action="AI_ASSESSMENT_OVERRIDE",
        entity_type="AI_ANALYSIS",
        entity_id=ai_record.id,
        user_id=current_user.id,
        details={
            "new_category": data.category.value if data.category else None,
            "new_priority": data.priority.value if data.priority else None,
            "reason": data.override_reason
        }
    )

    db.commit()
    db.refresh(complaint)
    return complaint

@router.post("/complaints/{complaint_id}/resolution", response_model=ComplaintResponse)
def submit_resolution(
    complaint_id: str,
    data: ResolutionSubmitRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_any_staff),
    db: Session = Depends(get_db)
):
    """
    Stage 1 Verification: Field crew or staff submits completion details and repair notes.
    Transitions complaint to AWAITING_CITIZEN_CONFIRMATION and alerts the citizen.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    resolution = ResolutionSubmission(
        complaint_id=complaint.id,
        submitted_by_id=current_user.id,
        resolution_notes=data.resolution_notes
    )
    db.add(resolution)

    old_status = complaint.status
    complaint.status = ComplaintStatus.AWAITING_CITIZEN_CONFIRMATION.value

    history = ComplaintStatusHistory(
        complaint_id=complaint.id,
        from_status=old_status,
        to_status=ComplaintStatus.AWAITING_CITIZEN_CONFIRMATION.value,
        changed_by_id=current_user.id,
        change_reason="Field repair submitted by staff",
        notes=data.resolution_notes
    )
    db.add(history)

    # Notify Citizen that repair is completed and awaiting their approval
    send_notification(
        db=db,
        user_id=complaint.citizen_id,
        title="Repair Completed — Please Verify",
        message=f"Remediation on #{complaint.reference_number} is completed. Please review after-repair evidence and confirm.",
        notification_type=NotificationType.RESOLUTION_READY.value,
        complaint_id=complaint.id
    )

    log_audit(
        db=db,
        action="RESOLUTION_SUBMITTED",
        entity_type="COMPLAINT",
        entity_id=complaint.id,
        user_id=current_user.id,
        details={"notes": data.resolution_notes}
    )

    db.commit()
    db.refresh(complaint)

    # Enqueue async email verification request (non-blocking)
    if complaint.citizen and complaint.citizen.email:
        background_tasks.add_task(
            email_service.send_resolution_awaiting_verification,
            to_email=complaint.citizen.email,
            citizen_name=complaint.citizen.full_name or "Citizen",
            reference_number=complaint.reference_number,
            completion_notes=data.resolution_notes,
            complaint_id=complaint.id
        )

    return complaint

# ----------------- MAP DATA -----------------

@router.get("/map/complaints")
def get_map_complaints(
    category: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    department_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(require_any_staff),
    db: Session = Depends(get_db)
):
    """
    Spatial complaints feed for Leaflet interactive map with markers and status metadata.
    Enforces role and department authorization boundaries:
    - Field Crews: See only their assigned complaints on the map.
    - Municipal Members: Scoped to their department.
    - Government Admin: Full map overview.
    """
    query = db.query(Complaint)

    if current_user.role == UserRole.FIELD_CREW.value:
        query = query.filter(Complaint.assigned_crew_id == current_user.id)
    elif current_user.role == UserRole.MUNICIPAL_MEMBER.value:
        if current_user.department_membership:
            user_dept_id = current_user.department_membership.department_id
            if department_id and department_id != user_dept_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
            query = query.filter(or_(Complaint.department_id == user_dept_id, Complaint.department_id == None))

    if category:
        query = query.filter(Complaint.category == category)
    if status:
        query = query.filter(Complaint.status == status)
    if priority:
        query = query.filter(Complaint.priority == priority)
    if department_id:
        query = query.filter(Complaint.department_id == department_id)
    if date_from:
        try:
            d_from = datetime.fromisoformat(date_from)
            query = query.filter(Complaint.created_at >= d_from)
        except Exception:
            pass
    if date_to:
        try:
            d_to = datetime.fromisoformat(date_to)
            query = query.filter(Complaint.created_at <= d_to)
        except Exception:
            pass

    complaints = query.all()
    features = []
    for c in complaints:
        features.append({
            "id": c.id,
            "reference_number": c.reference_number,
            "title": c.title,
            "category": c.category,
            "status": c.status,
            "priority": c.priority,
            "latitude": c.latitude,
            "longitude": c.longitude,
            "address": c.address,
            "created_at": c.created_at.isoformat(),
            "has_attachments": len(c.attachments) > 0,
            "first_image": c.attachments[0].file_path if c.attachments else None
        })
    return {"complaints": features}

# ----------------- USER ADMINISTRATION & RBAC -----------------

@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_staff_user(
    data: StaffCreateRequest,
    current_user: User = Depends(require_government_admin),
    db: Session = Depends(get_db)
):
    """
    Government Admin creates authorized Municipal Members or Field Crews.
    Refuses creation of a second Government Admin (Single Admin Invariant).
    """
    if data.role == UserRole.GOVERNMENT_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create a second Government Admin. Exactly one Government Admin is permitted."
        )

    # Check email duplicate
    existing = db.query(User).filter(User.email == data.email.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )

    dept = db.query(MunicipalDepartment).filter(MunicipalDepartment.id == data.department_id).first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Specified department not found")

    hashed_pwd = get_password_hash(data.password)
    user = User(
        email=data.email.lower(),
        full_name=data.full_name,
        phone_number=data.phone_number,
        hashed_password=hashed_pwd,
        role=data.role.value,
        is_active=True,
        is_verified=True
    )
    db.add(user)
    db.flush()

    if data.role == UserRole.MUNICIPAL_MEMBER:
        membership = DepartmentMembership(
            user_id=user.id,
            department_id=dept.id,
            designation=data.designation or "Municipal Staff",
            jurisdiction=data.jurisdiction or "City-wide",
            can_assign=True,
            can_verify=True
        )
        db.add(membership)
    elif data.role == UserRole.FIELD_CREW:
        crew = CrewProfile(
            user_id=user.id,
            department_id=dept.id,
            vehicle_number=data.vehicle_number,
            contact_number=data.contact_number,
            active_task_count=0
        )
        db.add(crew)

    log_audit(
        db=db,
        action="STAFF_ACCOUNT_CREATED",
        entity_type="USER",
        entity_id=user.id,
        user_id=current_user.id,
        details={"role": data.role.value, "department": dept.name}
    )

    db.commit()
    db.refresh(user)
    return user

@router.get("/users", response_model=List[UserResponse])
def list_users(
    role: Optional[str] = None,
    current_user: User = Depends(require_government_admin),
    db: Session = Depends(get_db)
):
    """Government Admin lists all users in the system."""
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    return query.order_by(User.created_at.desc()).all()

@router.post("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: str,
    current_user: User = Depends(require_government_admin),
    db: Session = Depends(get_db)
):
    """Deactivates an account and revokes active access."""
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate your own administrator account")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = False
    
    log_audit(
        db=db,
        action="USER_DEACTIVATED",
        entity_type="USER",
        entity_id=user.id,
        user_id=current_user.id
    )

    db.commit()
    return {"message": f"User {user.email} deactivated successfully"}

# ----------------- DEPARTMENTS -----------------

@router.get("/departments", response_model=List[DepartmentResponse])
def get_departments(
    current_user: User = Depends(require_any_staff),
    db: Session = Depends(get_db)
):
    """Lists all municipal departments with complaint counts."""
    departments = db.query(MunicipalDepartment).all()
    results = []
    for d in departments:
        members_count = db.query(DepartmentMembership).filter(DepartmentMembership.department_id == d.id).count()
        crews_count = db.query(CrewProfile).filter(CrewProfile.department_id == d.id).count()
        open_count = db.query(Complaint).filter(Complaint.department_id == d.id, Complaint.status.notin_(["RESOLVED", "CANCELLED"])).count()
        
        results.append(DepartmentResponse(
            id=d.id,
            name=d.name,
            code=d.code,
            description=d.description,
            contact_email=d.contact_email,
            contact_phone=d.contact_phone,
            is_active=d.is_active,
            created_at=d.created_at,
            member_count=members_count,
            crew_count=crews_count,
            open_complaints_count=open_count
        ))
    return results

@router.post("/departments", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def create_department(
    data: DepartmentCreate,
    current_user: User = Depends(require_government_admin),
    db: Session = Depends(get_db)
):
    """Government Admin creates a new municipal department."""
    existing = db.query(MunicipalDepartment).filter(
        or_(MunicipalDepartment.name == data.name, MunicipalDepartment.code == data.code.upper())
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department with this name or code already exists")

    dept = MunicipalDepartment(
        name=data.name,
        code=data.code.upper(),
        description=data.description,
        contact_email=data.contact_email,
        contact_phone=data.contact_phone,
        is_active=True
    )
    db.add(dept)
    db.commit()
    db.refresh(dept)

    log_audit(
        db=db,
        action="DEPARTMENT_CREATED",
        entity_type="MUNICIPAL_DEPARTMENT",
        entity_id=dept.id,
        user_id=current_user.id,
        details={"name": dept.name, "code": dept.code}
    )

    return DepartmentResponse(
        id=dept.id,
        name=dept.name,
        code=dept.code,
        description=dept.description,
        contact_email=dept.contact_email,
        contact_phone=dept.contact_phone,
        is_active=dept.is_active,
        created_at=dept.created_at,
        member_count=0,
        crew_count=0,
        open_complaints_count=0
    )

# ----------------- WORK ORDERS & FIELD CREWS -----------------

@router.get("/work-orders", response_model=List[WorkOrderResponse])
def get_work_orders(
    status: Optional[str] = None,
    current_user: User = Depends(require_any_staff),
    db: Session = Depends(get_db)
):
    """
    Returns work orders.
    Field Crews only see their own assigned work orders.
    Staff and Admin see all department work orders.
    """
    query = db.query(WorkOrder)

    if current_user.role == UserRole.FIELD_CREW.value:
        query = query.filter(WorkOrder.crew_id == current_user.id)

    if status:
        query = query.filter(WorkOrder.status == status)

    work_orders = query.order_by(WorkOrder.created_at.desc()).all()
    results = []
    for wo in work_orders:
        c = wo.complaint
        d = wo.department
        crew = wo.crew
        results.append(WorkOrderResponse(
            id=wo.id,
            complaint_id=wo.complaint_id,
            complaint_reference=c.reference_number if c else None,
            complaint_title=c.title if c else None,
            complaint_address=c.address if c else None,
            complaint_latitude=c.latitude if c else None,
            complaint_longitude=c.longitude if c else None,
            complaint_priority=c.priority if c else None,
            department_id=wo.department_id,
            department_name=d.name if d else None,
            crew_id=wo.crew_id,
            crew_name=crew.full_name if crew else None,
            title=wo.title,
            instructions=wo.instructions,
            status=wo.status,
            blocker_reason=wo.blocker_reason,
            scheduled_date=wo.scheduled_date,
            completion_date=wo.completion_date,
            created_at=wo.created_at,
            updated_at=wo.updated_at,
            updates=[]
        ))
    return results

@router.post("/work-orders", response_model=WorkOrderResponse, status_code=status.HTTP_201_CREATED)
def create_work_order(
    data: WorkOrderCreate,
    current_user: User = Depends(require_municipal_staff),
    db: Session = Depends(get_db)
):
    """Staff dispatches work order to an authorized field crew."""
    complaint = db.query(Complaint).filter(Complaint.id == data.complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    crew = db.query(User).filter(User.id == data.crew_id, User.role == UserRole.FIELD_CREW.value).first()
    if not crew:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field crew member not found")

    dept = db.query(MunicipalDepartment).filter(MunicipalDepartment.id == data.department_id).first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    wo = WorkOrder(
        complaint_id=complaint.id,
        department_id=dept.id,
        crew_id=crew.id,
        title=data.title,
        instructions=data.instructions,
        status=WorkOrderStatus.ASSIGNED.value,
        scheduled_date=data.scheduled_date or datetime.now(timezone.utc)
    )
    db.add(wo)

    # Link crew to complaint and update status
    complaint.assigned_crew_id = crew.id
    complaint.status = ComplaintStatus.IN_PROGRESS.value

    # Update crew active task count
    if crew.crew_profile:
        crew.crew_profile.active_task_count += 1

    history = ComplaintStatusHistory(
        complaint_id=complaint.id,
        from_status=ComplaintStatus.ASSIGNED.value,
        to_status=ComplaintStatus.IN_PROGRESS.value,
        changed_by_id=current_user.id,
        change_reason=f"Work order dispatched to field crew {crew.full_name}",
        notes=data.instructions
    )
    db.add(history)

    # Notify crew
    send_notification(
        db=db,
        user_id=crew.id,
        title="New Work Order Assigned",
        message=f"Work order #{complaint.reference_number}: {data.title} assigned to you.",
        notification_type=NotificationType.WORK_ORDER_ASSIGNED.value,
        complaint_id=complaint.id
    )

    log_audit(
        db=db,
        action="WORK_ORDER_CREATED",
        entity_type="WORK_ORDER",
        entity_id=wo.id,
        user_id=current_user.id,
        details={"crew_id": crew.id, "complaint_id": complaint.id}
    )

    db.commit()
    db.refresh(wo)

    return WorkOrderResponse(
        id=wo.id,
        complaint_id=wo.complaint_id,
        complaint_reference=complaint.reference_number,
        complaint_title=complaint.title,
        complaint_address=complaint.address,
        complaint_latitude=complaint.latitude,
        complaint_longitude=complaint.longitude,
        complaint_priority=complaint.priority,
        department_id=dept.id,
        department_name=dept.name,
        crew_id=crew.id,
        crew_name=crew.full_name,
        title=wo.title,
        instructions=wo.instructions,
        status=wo.status,
        blocker_reason=wo.blocker_reason,
        scheduled_date=wo.scheduled_date,
        completion_date=wo.completion_date,
        created_at=wo.created_at,
        updated_at=wo.updated_at,
        updates=[]
    )

@router.patch("/work-orders/{work_order_id}/status", response_model=WorkOrderResponse)
def update_work_order_status(
    work_order_id: str,
    data: WorkOrderStatusUpdate,
    current_user: User = Depends(require_any_staff),
    db: Session = Depends(get_db)
):
    """Field crew updates work order progress or reports blockers."""
    wo = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not wo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work order not found")

    if current_user.role == UserRole.FIELD_CREW.value and wo.crew_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only update your assigned work orders")

    wo.status = data.status.value
    if data.blocker_reason:
        wo.blocker_reason = data.blocker_reason
    if data.status == WorkOrderStatus.COMPLETED:
        wo.completion_date = datetime.now(timezone.utc)
        if wo.crew and wo.crew.crew_profile:
            wo.crew.crew_profile.active_task_count = max(0, wo.crew.crew_profile.active_task_count - 1)

    update_entry = WorkOrderUpdate(
        work_order_id=wo.id,
        updated_by_id=current_user.id,
        note=data.note,
        status=data.status.value
    )
    db.add(update_entry)

    log_audit(
        db=db,
        action="WORK_ORDER_STATUS_UPDATE",
        entity_type="WORK_ORDER",
        entity_id=wo.id,
        user_id=current_user.id,
        details={"new_status": data.status.value, "note": data.note}
    )

    db.commit()
    db.refresh(wo)

    c = wo.complaint
    return WorkOrderResponse(
        id=wo.id,
        complaint_id=wo.complaint_id,
        complaint_reference=c.reference_number if c else None,
        complaint_title=c.title if c else None,
        complaint_address=c.address if c else None,
        complaint_latitude=c.latitude if c else None,
        complaint_longitude=c.longitude if c else None,
        complaint_priority=c.priority if c else None,
        department_id=wo.department_id,
        department_name=wo.department.name if wo.department else None,
        crew_id=wo.crew_id,
        crew_name=wo.crew.full_name if wo.crew else None,
        title=wo.title,
        instructions=wo.instructions,
        status=wo.status,
        blocker_reason=wo.blocker_reason,
        scheduled_date=wo.scheduled_date,
        completion_date=wo.completion_date,
        created_at=wo.created_at,
        updated_at=wo.updated_at,
        updates=[]
    )

@router.post("/work-orders/{work_order_id}/accept", response_model=WorkOrderResponse)
def accept_work_order(
    work_order_id: str,
    current_user: User = Depends(require_any_staff),
    db: Session = Depends(get_db)
):
    """Field crew explicitly accepts an assigned work order."""
    wo = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not wo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work order not found")

    if current_user.role == UserRole.FIELD_CREW.value and wo.crew_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Work order not assigned to you")

    wo.status = WorkOrderStatus.ACCEPTED.value
    wo.updated_at = datetime.now(timezone.utc)

    update_entry = WorkOrderUpdate(
        work_order_id=wo.id,
        updated_by_id=current_user.id,
        note="Field crew accepted assignment and scheduled work",
        status=WorkOrderStatus.ACCEPTED.value
    )
    db.add(update_entry)
    db.commit()
    db.refresh(wo)

    c = wo.complaint
    return WorkOrderResponse(
        id=wo.id,
        complaint_id=wo.complaint_id,
        complaint_reference=c.reference_number if c else None,
        complaint_title=c.title if c else None,
        complaint_address=c.address if c else None,
        complaint_latitude=c.latitude if c else None,
        complaint_longitude=c.longitude if c else None,
        complaint_priority=c.priority if c else None,
        department_id=wo.department_id,
        department_name=wo.department.name if wo.department else None,
        crew_id=wo.crew_id,
        crew_name=wo.crew.full_name if wo.crew else None,
        title=wo.title,
        instructions=wo.instructions,
        status=wo.status,
        blocker_reason=wo.blocker_reason,
        scheduled_date=wo.scheduled_date,
        completion_date=wo.completion_date,
        created_at=wo.created_at,
        updated_at=wo.updated_at,
        updates=[]
    )

@router.post("/work-orders/{work_order_id}/submit-evidence", response_model=WorkOrderResponse)
def submit_work_order_evidence(
    work_order_id: str,
    data: WorkOrderSubmitEvidenceRequest,
    current_user: User = Depends(require_any_staff),
    db: Session = Depends(get_db)
):
    """
    Field crew marks on-site repair work finished and submits completion notes.
    Transitions complaint to WORK_COMPLETED_PENDING_REVIEW for municipal verification.
    """
    wo = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not wo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work order not found")

    if current_user.role == UserRole.FIELD_CREW.value and wo.crew_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Work order not assigned to you")

    wo.status = WorkOrderStatus.WORK_COMPLETED_PENDING_REVIEW.value
    wo.completion_date = datetime.now(timezone.utc)
    if wo.crew and wo.crew.crew_profile:
        wo.crew.crew_profile.active_task_count = max(0, wo.crew.crew_profile.active_task_count - 1)

    # Record update
    update_entry = WorkOrderUpdate(
        work_order_id=wo.id,
        updated_by_id=current_user.id,
        note=f"Work completed. Notes: {data.completion_notes}" + (f" | Materials: {data.materials_used}" if data.materials_used else ""),
        status=WorkOrderStatus.WORK_COMPLETED_PENDING_REVIEW.value
    )
    db.add(update_entry)

    # Also record ResolutionSubmission on complaint
    resolution = ResolutionSubmission(
        complaint_id=wo.complaint_id,
        work_order_id=wo.id,
        submitted_by_id=current_user.id,
        resolution_notes=data.completion_notes
    )
    db.add(resolution)

    # Transition complaint to WORK_COMPLETED_PENDING_REVIEW
    complaint = wo.complaint
    if complaint:
        old_status = complaint.status
        complaint.status = ComplaintStatus.WORK_COMPLETED_PENDING_REVIEW.value
        history = ComplaintStatusHistory(
            complaint_id=complaint.id,
            from_status=old_status,
            to_status=ComplaintStatus.WORK_COMPLETED_PENDING_REVIEW.value,
            changed_by_id=current_user.id,
            change_reason="Field crew submitted repair completion evidence",
            notes=data.completion_notes
        )
        db.add(history)

    db.commit()
    db.refresh(wo)

    c = wo.complaint
    return WorkOrderResponse(
        id=wo.id,
        complaint_id=wo.complaint_id,
        complaint_reference=c.reference_number if c else None,
        complaint_title=c.title if c else None,
        complaint_address=c.address if c else None,
        complaint_latitude=c.latitude if c else None,
        complaint_longitude=c.longitude if c else None,
        complaint_priority=c.priority if c else None,
        department_id=wo.department_id,
        department_name=wo.department.name if wo.department else None,
        crew_id=wo.crew_id,
        crew_name=wo.crew.full_name if wo.crew else None,
        title=wo.title,
        instructions=wo.instructions,
        status=wo.status,
        blocker_reason=wo.blocker_reason,
        scheduled_date=wo.scheduled_date,
        completion_date=wo.completion_date,
        created_at=wo.created_at,
        updated_at=wo.updated_at,
        updates=[]
    )

# ----------------- DUPLICATE COMPLAINTS REVIEW -----------------

@router.get("/duplicates", response_model=List[PotentialDuplicateResponse])
def get_potential_duplicates(
    current_user: User = Depends(require_municipal_staff),
    db: Session = Depends(get_db)
):
    """Lists AI-detected spatial & semantic duplicate complaints."""
    duplicates = db.query(PotentialDuplicate).filter(PotentialDuplicate.status == "FLAGGED").all()
    results = []
    for d in duplicates:
        results.append(PotentialDuplicateResponse(
            id=d.id,
            primary_complaint_id=d.primary_complaint_id,
            primary_reference=d.primary_complaint.reference_number if d.primary_complaint else None,
            primary_title=d.primary_complaint.title if d.primary_complaint else None,
            duplicate_complaint_id=d.duplicate_complaint_id,
            duplicate_reference=d.duplicate_complaint.reference_number if d.duplicate_complaint else None,
            duplicate_title=d.duplicate_complaint.title if d.duplicate_complaint else None,
            similarity_score=d.similarity_score,
            distance_meters=d.distance_meters,
            reason=d.reason,
            status=d.status,
            created_at=d.created_at
        ))
    return results

@router.post("/duplicates/{duplicate_id}/review")
def review_duplicate(
    duplicate_id: str,
    data: DuplicateReviewRequest,
    current_user: User = Depends(require_municipal_staff),
    db: Session = Depends(get_db)
):
    """Staff decides whether to confirm merge or dismiss a flagged duplicate."""
    record = db.query(PotentialDuplicate).filter(PotentialDuplicate.id == duplicate_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Duplicate record not found")

    record.status = data.status.value
    record.reviewed_by_id = current_user.id

    if data.status == DuplicateStatus.CONFIRMED_MERGED:
        dup_complaint = record.duplicate_complaint
        if dup_complaint:
            dup_complaint.status = ComplaintStatus.CANCELLED.value
            history = ComplaintStatusHistory(
                complaint_id=dup_complaint.id,
                from_status=dup_complaint.status,
                to_status=ComplaintStatus.CANCELLED.value,
                changed_by_id=current_user.id,
                change_reason=f"Merged as duplicate into #{record.primary_complaint.reference_number}",
                notes=data.review_notes
            )
            db.add(history)

    log_audit(
        db=db,
        action="DUPLICATE_REVIEWED",
        entity_type="POTENTIAL_DUPLICATE",
        entity_id=record.id,
        user_id=current_user.id,
        details={"decision": data.status.value, "notes": data.review_notes}
    )

    db.commit()
    return {"message": f"Duplicate record marked as {data.status.value}"}

# ----------------- CSV EXPORT & AUDIT LOGS -----------------

@router.get("/analytics/export-csv")
def export_complaints_csv(
    current_user: User = Depends(require_municipal_staff),
    db: Session = Depends(get_db)
):
    """Exports authorized complaint dataset to CSV format for municipal reporting."""
    complaints = db.query(Complaint).order_by(Complaint.created_at.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Reference Number", "Title", "Category", "Subcategory",
        "Status", "Priority", "Latitude", "Longitude", "Address",
        "Created At", "Updated At", "Department"
    ])

    for c in complaints:
        writer.writerow([
            c.reference_number,
            c.title,
            c.category,
            c.subcategory or "",
            c.status,
            c.priority,
            c.latitude,
            c.longitude,
            c.address or "",
            c.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            c.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            c.department.name if c.department else "Unassigned"
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=civicfix-complaints-{datetime.now().strftime('%Y%m%d')}.csv"}
    )

@router.get("/audit-logs", response_model=List[AuditLogResponse])
def get_audit_logs(
    limit: int = 100,
    current_user: User = Depends(require_government_admin),
    db: Session = Depends(get_db)
):
    """Government Admin reviews immutable audit trail."""
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    return logs

