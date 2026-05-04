import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.redis_client import get_redis
from ..models.rca import RCA
from ..models.work_item import WorkItem, WorkItemStatus
from ..patterns.state import validate_transition
from ..schemas.rca import RCACreate
from ..schemas.work_item import WorkItemCreate

logger = logging.getLogger(__name__)

DASHBOARD_CACHE_KEY = "dashboard:active_incidents"
DASHBOARD_CACHE_TTL = 30  # seconds


async def create_work_item(data: WorkItemCreate, db: AsyncSession) -> WorkItem:
    now = datetime.now(timezone.utc)
    work_item = WorkItem(
        component_id=data.component_id,
        component_type=data.component_type,
        title=data.title,
        severity=data.severity,
        description=data.description,
        status=WorkItemStatus.OPEN,
        created_at=now,
        updated_at=now,
    )
    db.add(work_item)
    await db.flush()
    await db.refresh(work_item)
    return work_item


async def get_work_item(work_item_id: str, db: AsyncSession) -> WorkItem | None:
    stmt = select(WorkItem).where(WorkItem.id == work_item_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_work_items(
    db: AsyncSession,
    status: WorkItemStatus | None = None,
    severity: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[WorkItem], int]:
    stmt = select(WorkItem)
    count_stmt = select(func.count(WorkItem.id))

    if status:
        stmt = stmt.where(WorkItem.status == status)
        count_stmt = count_stmt.where(WorkItem.status == status)
    if severity:
        stmt = stmt.where(WorkItem.severity == severity)
        count_stmt = count_stmt.where(WorkItem.severity == severity)

    # Sort by severity (P0 first), then by created_at (newest first)
    severity_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
    stmt = stmt.order_by(WorkItem.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    items_result = await db.execute(stmt)
    items = list(items_result.scalars().all())

    return items, total


async def transition_status(
    work_item_id: str,
    new_status: WorkItemStatus,
    db: AsyncSession,
) -> WorkItem:
    work_item = await get_work_item(work_item_id, db)
    if not work_item:
        raise ValueError(f"Work item {work_item_id} not found")

    has_rca = work_item.rca is not None
    validate_transition(
        current_status=WorkItemStatus(work_item.status),
        new_status=new_status,
        has_rca=has_rca,
    )

    work_item.status = new_status
    work_item.updated_at = datetime.now(timezone.utc)

    if new_status == WorkItemStatus.RESOLVED:
        work_item.resolved_at = datetime.now(timezone.utc)
        if work_item.rca:
            delta = work_item.resolved_at - work_item.created_at
            work_item.mttr_minutes = round(delta.total_seconds() / 60, 2)

    await db.flush()
    await db.refresh(work_item)

    # Invalidate dashboard cache
    redis = get_redis()
    await redis.delete(DASHBOARD_CACHE_KEY)

    logger.info(
        "Work item %s transitioned: %s → %s",
        work_item_id,
        work_item.status,
        new_status.value,
    )
    return work_item


async def submit_rca(
    work_item_id: str,
    rca_data: RCACreate,
    db: AsyncSession,
) -> RCA:
    work_item = await get_work_item(work_item_id, db)
    if not work_item:
        raise ValueError(f"Work item {work_item_id} not found")

    if work_item.status == WorkItemStatus.CLOSED:
        raise ValueError("Cannot modify RCA on a CLOSED work item")

    existing = await db.execute(
        select(RCA).where(RCA.work_item_id == work_item_id)
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"RCA already exists for work item {work_item_id}. Use PUT to update.")

    delta = rca_data.incident_end - rca_data.incident_start
    mttr_minutes = round(delta.total_seconds() / 60, 2)

    rca = RCA(
        work_item_id=work_item_id,
        incident_start=rca_data.incident_start,
        incident_end=rca_data.incident_end,
        root_cause_category=rca_data.root_cause_category,
        root_cause_detail=rca_data.root_cause_detail,
        fix_applied=rca_data.fix_applied,
        prevention_steps=rca_data.prevention_steps,
        impact_summary=rca_data.impact_summary,
        mttr_minutes=mttr_minutes,
        created_by=rca_data.created_by,
    )
    db.add(rca)

    work_item.mttr_minutes = mttr_minutes
    work_item.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(rca)

    redis = get_redis()
    await redis.delete(DASHBOARD_CACHE_KEY)

    logger.info("RCA submitted for work item %s. MTTR: %.1f min", work_item_id, mttr_minutes)
    return rca


async def refresh_dashboard_cache(db: AsyncSession) -> list[dict]:
    """Build and cache active incident summary for the dashboard hot-path."""
    stmt = (
        select(WorkItem)
        .where(WorkItem.status.in_([WorkItemStatus.OPEN.value, WorkItemStatus.INVESTIGATING.value]))
        .order_by(WorkItem.created_at.desc())
        .limit(100)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    data = []
    for item in items:
        data.append({
            "id": item.id,
            "component_id": item.component_id,
            "title": item.title,
            "severity": item.severity,
            "status": item.status,
            "signal_count": item.signal_count,
            "created_at": item.created_at.isoformat(),
        })

    redis = get_redis()
    await redis.setex(DASHBOARD_CACHE_KEY, DASHBOARD_CACHE_TTL, json.dumps(data))
    return data


async def get_dashboard_from_cache(db: AsyncSession) -> list[dict]:
    redis = get_redis()
    cached = await redis.get(DASHBOARD_CACHE_KEY)
    if cached:
        return json.loads(cached)
    return await refresh_dashboard_cache(db)
