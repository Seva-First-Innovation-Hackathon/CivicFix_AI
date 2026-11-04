from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class KeyMetrics(BaseModel):
    total_complaints: int
    active_complaints: int
    pending_review: int
    in_progress: int
    awaiting_citizen_confirmation: int
    resolved_complaints: int
    reopened_complaints: int
    high_priority_unresolved: int
    overdue_complaints: int
    average_resolution_hours: float
    citizen_satisfaction_rate: float

class CategoryCount(BaseModel):
    category: str
    count: int
    percentage: float

class PriorityCount(BaseModel):
    priority: str
    count: int
    percentage: float

class DepartmentCount(BaseModel):
    department_name: str
    count: int
    resolved_count: int

class TrendDataPoint(BaseModel):
    date: str
    submitted: int
    resolved: int

class AnalyticsOverview(BaseModel):
    metrics: KeyMetrics
    by_category: List[CategoryCount]
    by_priority: List[PriorityCount]
    by_department: List[DepartmentCount]
    trends: List[TrendDataPoint]

