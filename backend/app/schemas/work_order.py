from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.enums import WorkOrderStatus

class WorkOrderUpdateItem(BaseModel):
    id: str
    updated_by_id: str
    updated_by_name: Optional[str] = None
    note: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class WorkOrderCreate(BaseModel):
    complaint_id: str
    department_id: str
    crew_id: str
    title: str = Field(..., min_length=3, max_length=200)
    instructions: str = Field(..., min_length=5)
    scheduled_date: Optional[datetime] = None

class WorkOrderStatusUpdate(BaseModel):
    status: WorkOrderStatus
    note: str = Field(..., min_length=3)
    blocker_reason: Optional[str] = None

class WorkOrderResponse(BaseModel):
    id: str
    complaint_id: str
    complaint_reference: Optional[str] = None
    complaint_title: Optional[str] = None
    complaint_address: Optional[str] = None
    complaint_latitude: Optional[float] = None
    complaint_longitude: Optional[float] = None
    complaint_priority: Optional[str] = None
    department_id: str
    department_name: Optional[str] = None
    crew_id: str
    crew_name: Optional[str] = None
    title: str
    instructions: str
    status: str
    blocker_reason: Optional[str] = None
    scheduled_date: Optional[datetime] = None
    completion_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    updates: List[WorkOrderUpdateItem] = []

    class Config:
        from_attributes = True

class WorkOrderSubmitEvidenceRequest(BaseModel):
    completion_notes: str = Field(..., min_length=10, max_length=2000)
    materials_used: Optional[str] = None

