from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.enums import ComplaintCategory, PriorityLevel, ComplaintStatus, WorkOrderStatus

class AttachmentResponse(BaseModel):
    id: str
    file_name: str
    file_path: str
    file_size: int
    mime_type: str
    attachment_type: str
    is_internal: bool = False
    description: Optional[str] = None
    uploaded_by_id: str
    created_at: datetime

    class Config:
        from_attributes = True

class ComplaintCommentResponse(BaseModel):
    id: str
    complaint_id: str
    user_id: str
    user_name: Optional[str] = None
    user_role: Optional[str] = None
    content: str
    is_internal: bool = False
    comment_type: str
    created_at: datetime

    class Config:
        from_attributes = True

class AIAnalysisResponse(BaseModel):
    id: str
    provider: str
    model_name: str
    suggested_category: str
    suggested_subcategory: Optional[str] = None
    suggested_priority: str
    confidence_score: float
    safety_hazard_detected: bool
    urgency_level: str
    summary_explanation: str
    visual_findings: Optional[str] = None
    duplicate_checked: bool
    is_overridden: bool
    override_reason: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class StatusHistoryResponse(BaseModel):
    id: str
    from_status: Optional[str] = None
    to_status: str
    changed_by_id: Optional[str] = None
    changed_by_name: Optional[str] = None
    change_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class WorkOrderBrief(BaseModel):
    id: str
    title: str
    instructions: str
    status: str
    crew_name: Optional[str] = None
    crew_id: str
    created_at: datetime

    class Config:
        from_attributes = True

class ResolutionSubmissionResponse(BaseModel):
    id: str
    resolution_notes: str
    submitted_by_id: str
    submitted_by_name: Optional[str] = None
    submitted_at: datetime

    class Config:
        from_attributes = True

class ResolutionVerificationResponse(BaseModel):
    id: str
    is_satisfied: bool
    feedback_rating: Optional[int] = None
    feedback_notes: Optional[str] = None
    reopen_reason: Optional[str] = None
    verified_at: datetime

    class Config:
        from_attributes = True

class ComplaintCreateRequest(BaseModel):
    title: str = Field(..., min_length=5, max_length=150)
    description: str = Field(..., min_length=10, max_length=2000)
    category: ComplaintCategory = ComplaintCategory.OTHER
    subcategory: Optional[str] = Field(None, max_length=100)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    address: Optional[str] = Field(None, max_length=255)
    landmark: Optional[str] = Field(None, max_length=255)

class ComplaintResponse(BaseModel):
    id: str
    reference_number: str
    citizen_id: str
    citizen_name: Optional[str] = None
    title: str
    description: str
    category: str
    subcategory: Optional[str] = None
    latitude: float
    longitude: float
    address: Optional[str] = None
    landmark: Optional[str] = None
    status: str
    priority: str
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    assigned_crew_id: Optional[str] = None
    assigned_crew_name: Optional[str] = None
    is_disputed: bool
    sla_deadline: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    investigation_notes: Optional[str] = None
    clarification_requested: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    # Nested relations
    attachments: List[AttachmentResponse] = []
    ai_analysis: Optional[AIAnalysisResponse] = None
    status_history: List[StatusHistoryResponse] = []
    work_orders: List[WorkOrderBrief] = []
    resolution_submissions: List[ResolutionSubmissionResponse] = []
    resolution_verifications: List[ResolutionVerificationResponse] = []
    comments: List[ComplaintCommentResponse] = []

    class Config:
        from_attributes = True

class ComplaintListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    complaints: List[ComplaintResponse]

class ComplaintStatusUpdateRequest(BaseModel):
    status: ComplaintStatus
    reason: Optional[str] = None
    notes: Optional[str] = None

class ComplaintAssignmentRequest(BaseModel):
    department_id: str
    priority: Optional[PriorityLevel] = None
    notes: Optional[str] = None

class AIOverrideRequest(BaseModel):
    category: Optional[ComplaintCategory] = None
    priority: Optional[PriorityLevel] = None
    override_reason: str = Field(..., min_length=5)

class ResolutionSubmitRequest(BaseModel):
    resolution_notes: str = Field(..., min_length=10)

class CitizenConfirmResolutionRequest(BaseModel):
    is_satisfied: bool = True
    feedback_rating: Optional[int] = Field(None, ge=1, le=5)
    feedback_notes: Optional[str] = None
    reopen_reason: Optional[str] = None

class ComplaintCancelRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)

class ComplaintRejectRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)

class ComplaintClarificationRequest(BaseModel):
    information: str = Field(..., min_length=5, max_length=2000)

class ComplaintFlagInvestigationRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)

class ComplaintVerifyRequest(BaseModel):
    priority: PriorityLevel
    verification_notes: Optional[str] = None

class ReviewEvidenceRequest(BaseModel):
    is_approved: bool
    notes: str = Field(..., min_length=5, max_length=1000)

class ComplaintCommentCreateRequest(BaseModel):
    content: str = Field(..., min_length=2, max_length=2000)
    is_internal: bool = False
    comment_type: Optional[str] = "STAFF_PUBLIC_NOTE"

