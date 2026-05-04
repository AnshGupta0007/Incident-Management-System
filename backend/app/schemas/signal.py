from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Any
from ..models.work_item import Severity, ComponentType


class SignalIngest(BaseModel):
    component_id: str = Field(..., min_length=1, max_length=255, description="Unique component identifier")
    component_type: ComponentType = Field(default=ComponentType.API)
    signal_type: str = Field(..., description="error | latency | availability")
    severity: Severity = Field(default=Severity.P2)
    message: str = Field(..., min_length=1, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source_host: str | None = Field(None, max_length=255)

    @field_validator("signal_type")
    @classmethod
    def validate_signal_type(cls, v: str) -> str:
        allowed = {"error", "latency", "availability", "saturation"}
        if v not in allowed:
            raise ValueError(f"signal_type must be one of {allowed}")
        return v


class SignalResponse(BaseModel):
    accepted: bool = True
    stream_id: str
    message: str = "Signal queued for processing"


class SignalDocument(BaseModel):
    """MongoDB document schema for raw signals."""
    work_item_id: str | None
    component_id: str
    component_type: str
    signal_type: str
    severity: str
    message: str
    payload: dict[str, Any]
    timestamp: datetime
    source_host: str | None
    processed_at: datetime | None = None
