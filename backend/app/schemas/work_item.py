from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from ..models.work_item import WorkItemStatus, Severity, ComponentType
from .rca import RCAResponse


class WorkItemCreate(BaseModel):
    component_id: str
    component_type: ComponentType
    title: str
    severity: Severity
    description: str | None = None


class WorkItemUpdate(BaseModel):
    assigned_to: str | None = None
    description: str | None = None


class StatusTransitionRequest(BaseModel):
    new_status: WorkItemStatus
    note: str | None = Field(None, max_length=500)


class WorkItemResponse(BaseModel):
    id: str
    component_id: str
    component_type: str
    title: str
    description: str | None
    severity: str
    status: str
    signal_count: int
    assigned_to: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    mttr_minutes: float | None
    rca: Optional[RCAResponse] = None

    model_config = {"from_attributes": True}


class WorkItemListResponse(BaseModel):
    items: list[WorkItemResponse]
    total: int
    page: int
    page_size: int
