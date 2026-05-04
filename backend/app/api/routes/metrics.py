from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from ...core.database import get_db
from ...core.mongodb import get_mongo_db
from ...models.work_item import WorkItem, WorkItemStatus

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get("/timeseries", summary="Signal volume timeseries (MongoDB aggregation)")
async def get_signal_timeseries(
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> list[dict]:
    """
    Returns per-hour signal counts broken down by severity.
    Uses a MongoDB $group aggregation pipeline — this is the 'Sink (Aggregations)' tier.
    """
    mongo_db = get_mongo_db()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    pipeline = [
        {"$match": {"timestamp": {"$gte": since}}},
        {
            "$group": {
                "_id": {
                    "year":  {"$year": "$timestamp"},
                    "month": {"$month": "$timestamp"},
                    "day":   {"$dayOfMonth": "$timestamp"},
                    "hour":  {"$hour": "$timestamp"},
                },
                "total": {"$sum": 1},
                "P0": {"$sum": {"$cond": [{"$eq": ["$severity", "P0"]}, 1, 0]}},
                "P1": {"$sum": {"$cond": [{"$eq": ["$severity", "P1"]}, 1, 0]}},
                "P2": {"$sum": {"$cond": [{"$eq": ["$severity", "P2"]}, 1, 0]}},
                "P3": {"$sum": {"$cond": [{"$eq": ["$severity", "P3"]}, 1, 0]}},
                "P4": {"$sum": {"$cond": [{"$eq": ["$severity", "P4"]}, 1, 0]}},
            }
        },
        {"$sort": {"_id": 1}},
        {
            "$project": {
                "_id": 0,
                "time": {
                    "$dateToString": {
                        "format": "%Y-%m-%dT%H:00:00Z",
                        "date": {
                            "$dateFromParts": {
                                "year":  "$_id.year",
                                "month": "$_id.month",
                                "day":   "$_id.day",
                                "hour":  "$_id.hour",
                            }
                        },
                    }
                },
                "total": 1,
                "P0": 1, "P1": 1, "P2": 1, "P3": 1, "P4": 1,
            }
        },
    ]

    results = await mongo_db.signals.aggregate(pipeline).to_list(length=hours * 60)
    return results


@router.get("/summary", summary="Incident counts by status and severity")
async def get_summary(db: AsyncSession = Depends(get_db)) -> dict:
    """Live counts from PostgreSQL for the summary cards."""
    status_counts: dict[str, int] = {}
    for status in WorkItemStatus:
        result = await db.execute(
            select(func.count(WorkItem.id)).where(WorkItem.status == status)
        )
        status_counts[status.value] = result.scalar_one()

    severity_counts: dict[str, int] = {}
    for sev in ["P0", "P1", "P2", "P3", "P4"]:
        result = await db.execute(
            select(func.count(WorkItem.id))
            .where(WorkItem.severity == sev)
            .where(WorkItem.status.in_(["OPEN", "INVESTIGATING"]))
        )
        severity_counts[sev] = result.scalar_one()

    mttr_result = await db.execute(
        select(func.avg(WorkItem.mttr_minutes)).where(
            WorkItem.mttr_minutes.isnot(None)
        )
    )
    avg_mttr = mttr_result.scalar_one()

    return {
        "by_status": status_counts,
        "active_by_severity": severity_counts,
        "avg_mttr_minutes": round(avg_mttr, 1) if avg_mttr else None,
    }
