from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from app.models.enums import DuplicateStatus

class PotentialDuplicateResponse(BaseModel):
    id: str
    primary_complaint_id: str
    primary_reference: Optional[str] = None
    primary_title: Optional[str] = None
    duplicate_complaint_id: str
    duplicate_reference: Optional[str] = None
    duplicate_title: Optional[str] = None
    similarity_score: float
    distance_meters: float
    reason: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class DuplicateReviewRequest(BaseModel):
    status: DuplicateStatus  # CONFIRMED_MERGED or DISMISSED
    review_notes: Optional[str] = None

