from typing import Optional
from datetime import datetime
from pydantic import BaseModel

class NotificationResponse(BaseModel):
    id: str
    user_id: str
    title: str
    message: str
    notification_type: str
    complaint_id: Optional[str] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True

class NotificationPreferenceResponse(BaseModel):
    in_app_enabled: bool
    email_enabled: bool
    sms_enabled: bool

    class Config:
        from_attributes = True

class NotificationPreferenceUpdate(BaseModel):
    in_app_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None

