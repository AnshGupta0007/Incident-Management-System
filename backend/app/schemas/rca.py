from pydantic import BaseModel, Field, model_validator
from datetime import datetime
from ..models.rca import RootCauseCategory


class RCACreate(BaseModel):
    incident_start: datetime = Field(..., description="When the incident started")
    incident_end: datetime = Field(..., description="When the incident was resolved")
    root_cause_category: RootCauseCategory
    root_cause_detail: str = Field(..., min_length=20, max_length=5000, description="Detailed root cause")
    fix_applied: str = Field(..., min_length=10, max_length=5000, description="What fix was applied")
    prevention_steps: str = Field(..., min_length=10, max_length=5000, description="How to prevent recurrence")
    impact_summary: str | None = Field(None, max_length=2000)
    created_by: str | None = Field(None, max_length=255)

    @model_validator(mode="after")
    def validate_time_range(self) -> "RCACreate":
        if self.incident_end <= self.incident_start:
            raise ValueError("incident_end must be after incident_start")
        return self


class RCAResponse(BaseModel):
    id: str
    work_item_id: str
    incident_start: datetime
    incident_end: datetime
    root_cause_category: str
    root_cause_detail: str
    fix_applied: str
    prevention_steps: str
    impact_summary: str | None
    mttr_minutes: float | None
    created_by: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
