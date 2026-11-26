import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request, BackgroundTasks
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_user, require_citizen
from app.models.entities import (
    Complaint, ComplaintAttachment, User, ComplaintStatusHistory,
    ResolutionVerification, ComplaintComment
)
from app.models.enums import UserRole, ComplaintStatus, NotificationType, CommentType
from app.schemas.complaint import (
    ComplaintCreateRequest, ComplaintResponse, ComplaintListResponse,
    CitizenConfirmResolutionRequest, StatusHistoryResponse, AttachmentResponse,
    ComplaintCancelRequest, ComplaintClarificationRequest,
    ComplaintCommentResponse, ComplaintCommentCreateRequest
)
from app.services.storage.service import storage_service
from app.services.ai.service import run_ai_triage_background
from app.services.jobs.queue import create_outbox_job, dispatch_outbox_job, run_outbox_job_background
from app.services.audit import log_audit
from app.services.notifications.service import send_notification
from app.services.email.service import email_service
from app.services.complaints.lifecycle import execute_transition, enforce_complaint_staff_access
from app.core.config import settings
from app.core.limiter import limiter

router = APIRouter(prefix="/complaints", tags=["Complaints"])

MAX_REFERENCE_ATTEMPTS = 5


def generate_reference_number() -> str:
    """
    Generates a collision-resistant human-readable complaint reference number
    independent of table row counts. Format: CF-YYYY-XXXXXXXX.
    """
    year = datetime.now(timezone.utc).year
    unique_code = uuid.uuid4().hex[:8].upper()
    return f"CF-{year}-{unique_code}"


@router.post("", response_model=ComplaintResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_COMPLAINT_CREATE)
async def create_complaint(
    request: Request,
    data: ComplaintCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit a new civic complaint.
    Commits the complaint immediately with collision-safe reference generation and
    dispatches AI triage asynchronously in BackgroundTasks without blocking submission.
    """
    complaint = None
    ref_num = ""

    for attempt in range(MAX_REFERENCE_ATTEMPTS):
        ref_num = generate_reference_number()
        candidate = Complaint(
            reference_number=ref_num,
            citizen_id=current_user.id,
            title=data.title,
            description=data.description,
            category=data.category.value,
            subcategory=data.subcategory,
            latitude=data.latitude,
            longitude=data.longitude,
            address=data.address,
            landmark=data.landmark,
            status=ComplaintStatus.AI_ANALYSIS_PENDING.value,
            priority="P3",
            ai_processing_status="PENDING",
            ai_processing_attempts=0,
        )
        try:
            db.add(candidate)
            db.flush()

            db.add(ComplaintStatusHistory(
                complaint_id=candidate.id,
                from_status=None,
                to_status=ComplaintStatus.SUBMITTED.value,
                changed_by_id=current_user.id,
                change_reason="Complaint submitted by citizen",
                notes="Queued for automated AI assessment and triage",
            ))
            db.add(ComplaintStatusHistory(
                complaint_id=candidate.id,
                from_status=ComplaintStatus.SUBMITTED.value,
                to_status=ComplaintStatus.AI_ANALYSIS_PENDING.value,
                changed_by_id=None,
                change_reason="Enqueued for asynchronous AI analysis",
                notes="Background AI triage scheduled",
            ))
            log_audit(
                db=db,
                action="COMPLAINT_CREATED",
                entity_type="COMPLAINT",
                entity_id=candidate.id,
                user_id=current_user.id,
                details={"reference_number": ref_num, "category": candidate.category},
                ip_address=request.client.host if request.client else None,
                commit=False,
            )
            ai_job = create_outbox_job(
                db=db,
                job_type="ai_triage",
                dedup_key=f"ai_triage:{candidate.id}",
                complaint_id=candidate.id,
                payload={"complaint_id": candidate.id, "force": False},
                commit=False,
            )
            email_job = create_outbox_job(
                db=db,
                job_type="send_email",
                dedup_key=f"ack_email:{candidate.id}",
                complaint_id=candidate.id,
                payload={
                    "template": "submission_acknowledgment",
                    "to_email": current_user.email,
                    "citizen_name": current_user.full_name,
                    "reference_number": ref_num,
                    "title": candidate.title,
                    "category": candidate.category,
                    "complaint_id": candidate.id,
                },
                commit=False,
            )
            db.commit()
            complaint = candidate
            break
        except IntegrityError:
            db.rollback()
            if attempt == MAX_REFERENCE_ATTEMPTS - 1:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to allocate a unique complaint reference number. Please retry."
                )

    db.refresh(complaint)

    # Dispatch through Redis/ARQ durable worker queue when enabled, otherwise inline BackgroundTasks
    if (settings.QUEUE_BACKEND or "inline").lower() in {"redis", "arq"}:
        await dispatch_outbox_job(db=db, job=ai_job)
        await dispatch_outbox_job(db=db, job=email_job)
    else:
        background_tasks.add_task(run_ai_triage_background, complaint.id)
        background_tasks.add_task(run_outbox_job_background, email_job.id)

    return complaint


@router.get("/my", response_model=ComplaintListResponse)
def get_my_complaints(
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves complaints submitted exclusively by the authenticated citizen.
    Strict IDOR boundary: users can never view other citizens' complaints here.
    """
    query = db.query(Complaint).filter(Complaint.citizen_id == current_user.id)

    if status_filter:
        query = query.filter(Complaint.status == status_filter)

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


@router.get("/{complaint_id}", response_model=ComplaintResponse)
def get_complaint_by_id(
    complaint_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Fetches complaint details with full verification history.
    Enforces authorization across citizens, crews, and department staff,
    filtering out internal notes and internal investigation attachments for citizens.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    enforce_complaint_staff_access(db, current_user, complaint)

    if current_user.role == UserRole.CITIZEN.value:
        complaint.attachments = [a for a in complaint.attachments if not a.is_internal]
        complaint.comments = [c for c in complaint.comments if not c.is_internal]

    return complaint


@router.get("/{complaint_id}/timeline", response_model=List[StatusHistoryResponse])
def get_complaint_timeline(
    complaint_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Returns the immutable lifecycle history of a complaint."""
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    enforce_complaint_staff_access(db, current_user, complaint)

    history = (
        db.query(ComplaintStatusHistory)
        .filter(ComplaintStatusHistory.complaint_id == complaint_id)
        .order_by(ComplaintStatusHistory.created_at.asc())
        .all()
    )
    return history


@router.post("/{complaint_id}/attachments", response_model=AttachmentResponse)
async def upload_complaint_attachment(
    complaint_id: str,
    file: UploadFile = File(...),
    attachment_type: str = Form("CITIZEN_ORIGINAL"),
    description: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Uploads photographic evidence for a complaint with strict role/ownership authorization."""
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    enforce_complaint_staff_access(db, current_user, complaint)

    is_internal = False
    if current_user.role == UserRole.CITIZEN.value:
        folder = "complaints"
        att_type = "CITIZEN_ORIGINAL" if attachment_type in ["ORIGINAL", "CITIZEN_ORIGINAL"] else "CITIZEN_CLARIFICATION"
    else:
        folder = "resolutions" if "RESOLUTION" in attachment_type or "REPAIR" in attachment_type else "complaints"
        att_type = attachment_type

    saved = await storage_service.save_file_with_metadata(file, folder=folder)

    attachment = ComplaintAttachment(
        complaint_id=complaint.id,
        file_name=saved.file_name,
        file_path=saved.file_path,
        file_size=saved.file_size,
        mime_type=saved.mime_type,
        attachment_type=att_type,
        is_internal=is_internal,
        description=description,
        uploaded_by_id=current_user.id,
        storage_provider=saved.storage_provider,
        storage_object_key=saved.storage_object_key,
        sha256_checksum=saved.sha256_checksum,
        storage_verification_status=saved.storage_verification_status,
    )
    db.add(attachment)
    db.flush()

    log_audit(
        db=db,
        action="ATTACHMENT_UPLOADED",
        entity_type="COMPLAINT_ATTACHMENT",
        entity_id=attachment.id,
        user_id=current_user.id,
        details={
            "file_name": saved.file_name,
            "type": att_type,
            "storage_provider": saved.storage_provider,
        },
        commit=False,
    )
    db.commit()
    db.refresh(attachment)

    return attachment


@router.post("/{complaint_id}/cancel", response_model=ComplaintResponse)
def cancel_complaint(
    complaint_id: str,
    data: ComplaintCancelRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Citizen cancels an eligible complaint. Mandatory reason is permanently recorded."""
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    if current_user.role == UserRole.CITIZEN.value and complaint.citizen_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the reporting citizen can cancel this complaint")

    complaint = execute_transition(
        db=db,
        complaint=complaint,
        target_status=ComplaintStatus.CANCELLED.value,
        user=current_user,
        reason=data.reason,
        background_tasks=background_tasks
    )
    return complaint


@router.post("/{complaint_id}/clarify", response_model=ComplaintResponse)
def clarify_complaint(
    complaint_id: str,
    data: ComplaintClarificationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Citizen submits clarification when requested by municipal staff.
    Adds clarification to history and transitions complaint back to UNDER_REVIEW.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    if complaint.citizen_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the reporting citizen can provide clarification")

    if complaint.status != ComplaintStatus.AWAITING_CITIZEN_INFORMATION.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Complaint is in '{complaint.status}' status, not awaiting citizen information"
        )

    comment = ComplaintComment(
        complaint_id=complaint.id,
        user_id=current_user.id,
        content=data.information,
        is_internal=False,
        comment_type=CommentType.CITIZEN_CLARIFICATION.value
    )
    db.add(comment)

    complaint = execute_transition(
        db=db,
        complaint=complaint,
        target_status=ComplaintStatus.UNDER_REVIEW.value,
        user=current_user,
        reason="Citizen provided requested clarification",
        notes=data.information,
        background_tasks=background_tasks
    )
    return complaint


@router.get("/{complaint_id}/comments", response_model=List[ComplaintCommentResponse])
def get_complaint_comments(
    complaint_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lists comments and clarifications. Citizens never see internal staff notes."""
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    enforce_complaint_staff_access(db, current_user, complaint)

    query = db.query(ComplaintComment).filter(ComplaintComment.complaint_id == complaint_id)
    if current_user.role == UserRole.CITIZEN.value:
        query = query.filter(ComplaintComment.is_internal == False)

    comments = query.order_by(ComplaintComment.created_at.asc()).all()
    results = []
    for c in comments:
        results.append(ComplaintCommentResponse(
            id=c.id,
            complaint_id=c.complaint_id,
            user_id=c.user_id,
            user_name=c.author.full_name if c.author else "User",
            user_role=c.author.role if c.author else "CITIZEN",
            content=c.content,
            is_internal=c.is_internal,
            comment_type=c.comment_type,
            created_at=c.created_at
        ))
    return results


@router.post("/{complaint_id}/comments", response_model=ComplaintCommentResponse)
def add_complaint_comment(
    complaint_id: str,
    data: ComplaintCommentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Adds a public update or citizen clarification to the complaint."""
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    enforce_complaint_staff_access(db, current_user, complaint)

    is_internal = data.is_internal
    comment_type = data.comment_type or "STAFF_PUBLIC_NOTE"

    if current_user.role == UserRole.CITIZEN.value:
        is_internal = False
        comment_type = "CITIZEN_CLARIFICATION"

    comment = ComplaintComment(
        complaint_id=complaint.id,
        user_id=current_user.id,
        content=data.content,
        is_internal=is_internal,
        comment_type=comment_type
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
        is_internal=comment.is_internal,
        comment_type=comment.comment_type,
        created_at=comment.created_at
    )


@router.post("/{complaint_id}/confirm-resolution", response_model=ComplaintResponse)
def confirm_resolution(
    complaint_id: str,
    data: CitizenConfirmResolutionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_citizen),
    db: Session = Depends(get_db)
):
    """
    Stage 2 Verification: Citizen confirms official repair and marks complaint as RESOLVED.
    Can only be performed by the reporting citizen when status is AWAITING_CITIZEN_CONFIRMATION.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    if complaint.citizen_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the citizen who reported this issue can verify its resolution"
        )

    if complaint.status != ComplaintStatus.AWAITING_CITIZEN_CONFIRMATION.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot confirm resolution while complaint is in '{complaint.status}' status"
        )

    verification = ResolutionVerification(
        complaint_id=complaint.id,
        citizen_id=current_user.id,
        is_satisfied=True,
        feedback_rating=data.feedback_rating or 5,
        feedback_notes=data.feedback_notes or "Citizen confirmed resolution satisfactory"
    )
    db.add(verification)

    old_status = complaint.status
    complaint.status = ComplaintStatus.RESOLVED.value
    complaint.is_disputed = False

    db.add(ComplaintStatusHistory(
        complaint_id=complaint.id,
        from_status=old_status,
        to_status=ComplaintStatus.RESOLVED.value,
        changed_by_id=current_user.id,
        change_reason="Citizen verified and approved resolution",
        notes=f"Rating: {data.feedback_rating or 5}/5. Feedback: {data.feedback_notes or 'None'}"
    ))

    log_audit(
        db=db,
        action="RESOLUTION_CONFIRMED_BY_CITIZEN",
        entity_type="COMPLAINT",
        entity_id=complaint.id,
        user_id=current_user.id,
        details={"rating": data.feedback_rating},
        commit=False,
    )

    from app.services.jobs.queue import dispatch_or_execute_outbox_job

    email_job = create_outbox_job(
        db=db,
        job_type="send_email",
        dedup_key=f"res_verified_confirm:{complaint.id}",
        complaint_id=complaint.id,
        payload={
            "template": "resolution_verified",
            "to_email": current_user.email,
            "recipient_name": current_user.full_name,
            "reference_number": complaint.reference_number,
            "is_satisfied": True,
            "notes": data.feedback_notes,
            "complaint_id": complaint.id,
        },
        commit=False,
    )

    db.commit()
    db.refresh(complaint)
    background_tasks.add_task(dispatch_or_execute_outbox_job, email_job.id)

    return complaint


@router.post("/{complaint_id}/reopen", response_model=ComplaintResponse)
def reopen_complaint(
    complaint_id: str,
    data: CitizenConfirmResolutionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_citizen),
    db: Session = Depends(get_db)
):
    """Citizen reports that problem remains unresolved. Reopens complaint with recorded justification."""
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    if complaint.citizen_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the reporting citizen can contest resolution"
        )

    allowed_reopen_statuses = {
        ComplaintStatus.AWAITING_CITIZEN_CONFIRMATION.value,
        ComplaintStatus.RESOLVED.value,
    }
    if complaint.status not in allowed_reopen_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reopen complaint while in '{complaint.status}' status"
        )

    if not data.reopen_reason or len(data.reopen_reason.strip()) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A detailed reason is required to contest and reopen this complaint"
        )

    db.add(ResolutionVerification(
        complaint_id=complaint.id,
        citizen_id=current_user.id,
        is_satisfied=False,
        reopen_reason=data.reopen_reason,
        feedback_notes=data.feedback_notes
    ))

    old_status = complaint.status
    complaint.status = ComplaintStatus.REOPENED.value
    complaint.is_disputed = True

    db.add(ComplaintStatusHistory(
        complaint_id=complaint.id,
        from_status=old_status,
        to_status=ComplaintStatus.REOPENED.value,
        changed_by_id=current_user.id,
        change_reason="Citizen reported issue still exists",
        notes=data.reopen_reason
    ))

    send_notification(
        db=db,
        user_id=complaint.citizen_id,
        title="Complaint Reopened",
        message=f"Complaint #{complaint.reference_number} has been reopened for further remediation.",
        notification_type=NotificationType.REOPENED.value,
        complaint_id=complaint.id,
        commit=False,
    )

    log_audit(
        db=db,
        action="COMPLAINT_REOPENED_BY_CITIZEN",
        entity_type="COMPLAINT",
        entity_id=complaint.id,
        user_id=current_user.id,
        details={"reopen_reason": data.reopen_reason},
        commit=False,
    )

    from app.services.jobs.queue import dispatch_or_execute_outbox_job

    email_job = create_outbox_job(
        db=db,
        job_type="send_email",
        dedup_key=f"res_verified_reopen:{complaint.id}",
        complaint_id=complaint.id,
        payload={
            "template": "resolution_verified",
            "to_email": current_user.email,
            "recipient_name": current_user.full_name,
            "reference_number": complaint.reference_number,
            "is_satisfied": False,
            "notes": data.reopen_reason,
            "complaint_id": complaint.id,
        },
        commit=False,
    )

    db.commit()
    db.refresh(complaint)
    background_tasks.add_task(dispatch_or_execute_outbox_job, email_job.id)

    return complaint


@router.post("/{complaint_id}/reanalyze-ai", response_model=ComplaintResponse)
@limiter.limit(settings.RATE_LIMIT_AI_ANALYSIS)
async def reanalyze_complaint_ai(
    complaint_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Safely triggers or retries asynchronous AI triage on an existing complaint.
    Rejects duplicate concurrent processing cleanly (HTTP 409) when already in flight.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")

    enforce_complaint_staff_access(db, current_user, complaint)

    if complaint.ai_processing_status == "PROCESSING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AI analysis is already in progress for this complaint."
        )

    complaint.ai_processing_status = "PENDING"
    complaint.ai_processing_error = None
    ai_job = create_outbox_job(
        db=db,
        job_type="ai_triage",
        dedup_key=f"ai_triage_reanalyze:{complaint.id}",
        complaint_id=complaint.id,
        payload={"complaint_id": complaint.id, "force": True},
        commit=False,
    )
    db.commit()
    db.refresh(complaint)

    if (settings.QUEUE_BACKEND or "inline").lower() in {"redis", "arq"}:
        await dispatch_outbox_job(db=db, job=ai_job)
    else:
        background_tasks.add_task(run_ai_triage_background, complaint.id, True)
    return complaint
