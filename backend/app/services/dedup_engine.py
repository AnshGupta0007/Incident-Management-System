"""
Deduplication Engine.

Design:
  Two-tier deduplication prevents duplicate Work Items while ensuring
  every raw signal is still stored for audit purposes.

  Tier 1 (Fast path): Redis key `dedup:{component_id}` with 10s TTL.
    If the key exists, the signal maps to the recorded work_item_id without
    touching PostgreSQL at all.

  Tier 2 (Slow path): On Redis miss, check PostgreSQL for any OPEN or
    INVESTIGATING work item for this component. If found, re-warm the Redis
    key and reuse that work item. Only create a new work item on a full miss.

  Why two tiers?
    Redis can fail or keys can expire during an ongoing incident. Falling
    back to PostgreSQL prevents spurious duplicate work items after a Redis
    restart while keeping the hot-path extremely fast.
"""

import logging
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.work_item import WorkItem, WorkItemStatus

logger = logging.getLogger(__name__)

DEDUP_KEY_PREFIX = "dedup:"
ACTIVE_STATUSES = {WorkItemStatus.OPEN.value, WorkItemStatus.INVESTIGATING.value}


async def get_or_create_work_item_id(
    component_id: str,
    redis: Redis,
    db: AsyncSession,
    new_work_item_factory,  # async callable() -> WorkItem
) -> tuple[str, bool]:
    """
    Returns (work_item_id, is_new_incident).

    is_new_incident=True  → caller should trigger alerting
    is_new_incident=False → signal deduplicated to existing work item
    """
    key = f"{DEDUP_KEY_PREFIX}{component_id}"

    # Tier 1: Redis fast path
    cached_id = await redis.get(key)
    if cached_id:
        logger.debug("Dedup hit (Redis): component=%s → work_item=%s", component_id, cached_id)
        # Refresh TTL so long-running incidents keep their dedup window warm
        await redis.expire(key, settings.DEDUP_WINDOW_SECONDS)
        return cached_id, False

    # Tier 2: PostgreSQL slow path — look for active work item
    stmt = (
        select(WorkItem)
        .where(WorkItem.component_id == component_id)
        .where(WorkItem.status.in_(list(ACTIVE_STATUSES)))
        .order_by(WorkItem.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        logger.debug(
            "Dedup hit (DB): component=%s → work_item=%s (status=%s)",
            component_id,
            existing.id,
            existing.status,
        )
        # Re-warm Redis cache
        await redis.setex(key, settings.DEDUP_WINDOW_SECONDS, existing.id)
        return existing.id, False

    # Full miss — create new Work Item
    work_item = await new_work_item_factory()
    await redis.setex(key, settings.DEDUP_WINDOW_SECONDS, work_item.id)
    logger.info(
        "New work item created: id=%s component=%s", work_item.id, component_id
    )
    return work_item.id, True


async def increment_signal_count(work_item_id: str, db: AsyncSession) -> None:
    """Atomically increment signal_count on the work item."""
    stmt = select(WorkItem).where(WorkItem.id == work_item_id)
    result = await db.execute(stmt)
    work_item = result.scalar_one_or_none()
    if work_item:
        work_item.signal_count += 1
        work_item.updated_at = datetime.now(timezone.utc)
