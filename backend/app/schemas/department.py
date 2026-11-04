from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr

class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = None
    jurisdiction: Optional[str] = "City-wide"
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None

class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    jurisdiction: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    is_active: Optional[bool] = None

class DepartmentResponse(BaseModel):
    id: str
    name: str
    code: str
    description: Optional[str] = None
    jurisdiction: Optional[str] = "City-wide"
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    is_active: bool
    created_at: datetime
    member_count: Optional[int] = 0
    crew_count: Optional[int] = 0
    open_complaints_count: Optional[int] = 0

    class Config:
        from_attributes = True

