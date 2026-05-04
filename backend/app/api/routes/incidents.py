import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.mongodb import get_mongo_db
from ...models.work_item import WorkItemStatus
from ...schemas.rca import RCACreate, RCAResponse
from ...schemas.work_item import (
    StatusTransitionRequest,
    WorkItemCreate,
    WorkItemListResponse,
    WorkItemResponse,
)
from ...services.incident_service import (
    create_work_item,
    get_dashboard_from_cache,
    get_work_item,
    list_work_items,
    submit_rca,
    transition_status,
)
from ...workers.websocket_manager import manager
import json

router = APIRouter(prefix="/incidents", tags=["Incidents"])
logger = logging.getLogger(__name__)


@router.get(
    "",
    response_model=WorkItemListResponse,
    summary="List all work items",
)
async def list_incidents(
    status: WorkItemStatus | None = Query(None),
    severity: str | None = Query(None),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_db),
) -> WorkItemListResponse:
    items, total = await list_work_items(db, status=status, severity=severity, page=page, page_size=page_size)
    return WorkItemListResponse(
        items=[WorkItemResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=WorkItemResponse,
    status_code=201,
    summary="Manually create a work item (escalation from external systems)",
)
async def create_incident(
    body: WorkItemCreate,
    db: AsyncSession = Depends(get_db),
) -> WorkItemResponse:
    item = await create_work_item(body, db)
    return WorkItemResponse.model_validate(item)


@router.get(
    "/dashboard",
    summary="Get live dashboard state (cached)",
)
async def get_dashboard(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Returns active incidents from Redis cache. Falls back to DB on miss."""
    return await get_dashboard_from_cache(db)


@router.get(
    "/{work_item_id}",
    response_model=WorkItemResponse,
    summary="Get work item details",
)
async def get_incident(
    work_item_id: str,
    db: AsyncSession = Depends(get_db),
) -> WorkItemResponse:
    item = await get_work_item(work_item_id, db)
    if not item:
        raise HTTPException(status_code=404, detail=f"Work item {work_item_id} not found")
    return WorkItemResponse.model_validate(item)


@router.get(
    "/{work_item_id}/signals",
    summary="Get raw signals for a work item (from MongoDB)",
)
async def get_incident_signals(
    work_item_id: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict]:
    mongo_db = get_mongo_db()
    cursor = (
        mongo_db.signals.find(
            {"work_item_id": work_item_id},
            {"_id": 0},
        )
        .sort("timestamp", -1)
        .limit(limit)
    )
    signals = await cursor.to_list(length=limit)
    # Convert datetime objects to ISO strings for JSON serialization
    for s in signals:
        for key, val in s.items():
            if hasattr(val, "isoformat"):
                s[key] = val.isoformat()
    return signals


@router.patch(
    "/{work_item_id}/status",
    response_model=WorkItemResponse,
    summary="Transition work item status",
)
async def update_status(
    work_item_id: str,
    body: StatusTransitionRequest,
    db: AsyncSession = Depends(get_db),
) -> WorkItemResponse:
    try:
        item = await transition_status(work_item_id, body.new_status, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Broadcast state change via WebSocket
    await manager.broadcast(json.dumps({
        "type": "status_changed",
        "work_item_id": work_item_id,
        "new_status": body.new_status.value,
    }))

    return WorkItemResponse.model_validate(item)


@router.post(
    "/{work_item_id}/rca",
    response_model=RCAResponse,
    status_code=201,
    summary="Submit Root Cause Analysis",
)
async def create_rca(
    work_item_id: str,
    rca_data: RCACreate,
    db: AsyncSession = Depends(get_db),
) -> RCAResponse:
    try:
        rca = await submit_rca(work_item_id, rca_data, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    await manager.broadcast(json.dumps({
        "type": "rca_submitted",
        "work_item_id": work_item_id,
    }))

    return RCAResponse.model_validate(rca)


@router.get(
    "/{work_item_id}/replay",
    summary="Replay incident signals in chronological order",
)
async def replay_incident(
    work_item_id: str,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> dict:
    """Returns all signals for the incident sorted ascending by timestamp for replay."""
    mongo_db = get_mongo_db()
    cursor = (
        mongo_db.signals.find(
            {"work_item_id": work_item_id},
            {"_id": 0},
        )
        .sort("timestamp", 1)
        .limit(limit)
    )
    signals = await cursor.to_list(length=limit)
    for s in signals:
        for key, val in s.items():
            if hasattr(val, "isoformat"):
                s[key] = val.isoformat()

    return {
        "work_item_id": work_item_id,
        "total_signals": len(signals),
        "timeline": signals,
    }
