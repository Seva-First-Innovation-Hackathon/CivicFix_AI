from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from app.models.enums import UserRole

class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    phone_number: Optional[str] = Field(None, max_length=20)

class CitizenRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: str = Field(..., min_length=2, max_length=100)
    phone_number: Optional[str] = Field(None, max_length=20)
    preferred_language: Optional[str] = Field("en", max_length=10)

class StaffCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: str = Field(..., min_length=2, max_length=100)
    phone_number: Optional[str] = Field(None, max_length=20)
    role: UserRole  # Must be MUNICIPAL_MEMBER or FIELD_CREW
    department_id: str
    designation: Optional[str] = "Municipal Officer"
    jurisdiction: Optional[str] = "City-wide"
    vehicle_number: Optional[str] = None
    contact_number: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    full_name: str
    role: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class CitizenProfileResponse(BaseModel):
    preferred_language: str
    address: Optional[str] = None
    emergency_contact: Optional[str] = None

    class Config:
        from_attributes = True

class DepartmentMembershipResponse(BaseModel):
    department_id: str
    department_name: Optional[str] = None
    designation: str
    jurisdiction: Optional[str] = "City-wide"
    can_assign: bool
    can_verify: bool

    class Config:
        from_attributes = True

class CrewProfileResponse(BaseModel):
    department_id: str
    department_name: Optional[str] = None
    vehicle_number: Optional[str] = None
    contact_number: Optional[str] = None
    active_task_count: int

    class Config:
        from_attributes = True

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    phone_number: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    citizen_profile: Optional[CitizenProfileResponse] = None
    department_membership: Optional[DepartmentMembershipResponse] = None
    crew_profile: Optional[CrewProfileResponse] = None

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    preferred_language: Optional[str] = None
    is_active: Optional[bool] = None

