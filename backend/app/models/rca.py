from sqlalchemy import String, DateTime, Text, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import uuid
import enum
from datetime import datetime
from ..core.database import Base


class RootCauseCategory(str, enum.Enum):
    INFRASTRUCTURE = "INFRASTRUCTURE"
    CODE_BUG = "CODE_BUG"
    CONFIGURATION = "CONFIGURATION"
    CAPACITY = "CAPACITY"
    DEPENDENCY = "DEPENDENCY"
    HUMAN_ERROR = "HUMAN_ERROR"
    SECURITY = "SECURITY"
    UNKNOWN = "UNKNOWN"


class RCA(Base):
    __tablename__ = "rcas"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    work_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("work_items.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    incident_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    incident_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    root_cause_category: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    root_cause_detail: Mapped[str] = mapped_column(Text, nullable=False)
    fix_applied: Mapped[str] = mapped_column(Text, nullable=False)
    prevention_steps: Mapped[str] = mapped_column(Text, nullable=False)
    impact_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    mttr_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    work_item: Mapped["WorkItem"] = relationship(  # noqa: F821
        "WorkItem", back_populates="rca"
    )
