from sqlalchemy import String, Integer, DateTime, Text, Enum as SAEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import uuid
import enum
from datetime import datetime
from ..core.database import Base


class WorkItemStatus(str, enum.Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class Severity(str, enum.Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class ComponentType(str, enum.Enum):
    RDBMS = "RDBMS"
    CACHE = "CACHE"
    API = "API"
    QUEUE = "QUEUE"
    NOSQL = "NOSQL"
    MCP_HOST = "MCP_HOST"


class WorkItem(Base):
    __tablename__ = "work_items"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    component_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    component_type: Mapped[str] = mapped_column(
        SAEnum(ComponentType), nullable=False, default=ComponentType.API
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(
        SAEnum(Severity), nullable=False, default=Severity.P2
    )
    status: Mapped[str] = mapped_column(
        SAEnum(WorkItemStatus), nullable=False, default=WorkItemStatus.OPEN
    )
    signal_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mttr_minutes: Mapped[float | None] = mapped_column(nullable=True)

    rca: Mapped["RCA"] = relationship(  # noqa: F821
        "RCA", back_populates="work_item", uselist=False, lazy="selectin"
    )

    __table_args__ = (
        Index("ix_work_items_status_severity", "status", "severity"),
        Index("ix_work_items_component_status", "component_id", "status"),
    )
