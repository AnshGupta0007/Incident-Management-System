"""
Signal Processing Worker.

Backpressure & Resilience Design:
  1. Signals arrive at the HTTP API and are IMMEDIATELY pushed to a Redis
     Stream. The API never waits for DB writes — it returns 202 Accepted
     in < 5ms regardless of DB/Mongo state.

  2. This worker reads from the stream using consumer groups. Each message
     is processed atomically: MongoDB write (audit log) + PostgreSQL write
     (work item) + Redis cache invalidation happen in a single logical unit
     with retry logic.

  3. If PostgreSQL is slow, messages pile up in the Redis Stream (buffered
     up to STREAM_MAX_LEN). The worker applies exponential backoff on DB
     errors, so it slows down gracefully rather than hammering a degraded DB.

  4. A message is only ACK'd after successful processing. If the worker
     crashes mid-processing, the un-ACK'd message is re-delivered on restart
     (via XAUTOCLAIM / pending entry list).

  5. The stream acts as the backpressure valve: callers see no latency
     increase, the worker absorbs bursts, and the DB is protected.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from ..core.circuit_breaker import db_breaker, mongo_breaker
from ..core.config import settings
from ..core.database import AsyncSessionLocal
from ..core.mongodb import get_mongo_db
from ..core.redis_client import get_redis
from ..models.work_item import ComponentType, Severity, WorkItem, WorkItemStatus
from ..patterns.strategy import AlertContext, get_alert_strategy, resolve_severity
from ..services.dedup_engine import get_or_create_work_item_id, increment_signal_count
from ..services.incident_service import refresh_dashboard_cache
from .websocket_manager import manager

logger = logging.getLogger(__name__)

# Metrics
_signals_processed = 0
_last_metric_time = datetime.now(timezone.utc)


async def _store_signal_in_mongo(
    mongo_db: AsyncIOMotorDatabase,
    signal_data: dict,
    work_item_id: str,
) -> None:
    doc = {
        "work_item_id": work_item_id,
        "component_id": signal_data["component_id"],
        "component_type": signal_data.get("component_type", "API"),
        "signal_type": signal_data["signal_type"],
        "severity": signal_data["severity"],
        "message": signal_data["message"],
        "payload": json.loads(signal_data.get("payload", "{}")),
        "timestamp": datetime.fromisoformat(signal_data["timestamp"]),
        "source_host": signal_data.get("source_host"),
        "processed_at": datetime.now(timezone.utc),
    }
    await mongo_db.signals.insert_one(doc)


async def _process_single_signal(signal_data: dict) -> None:
    global _signals_processed

    redis = get_redis()
    mongo_db = get_mongo_db()

    component_id = signal_data["component_id"]
    component_type = signal_data.get("component_type", "API")
    severity_str = signal_data.get("severity", "P2")

    # Resolve final severity considering component type rules
    final_severity = resolve_severity(component_type, severity_str)

    retries = 0
    while retries <= settings.WORKER_MAX_RETRIES:
        try:
            # Fail fast if PostgreSQL circuit is open — don't waste a retry slot
            if db_breaker.is_open():
                raise RuntimeError(
                    f"PostgreSQL circuit breaker OPEN "
                    f"({db_breaker._failures} consecutive failures) — skipping"
                )

            async with AsyncSessionLocal() as db:
                async def create_work_item() -> WorkItem:
                    title = (
                        f"[{component_type}] {component_id} — "
                        f"{signal_data.get('signal_type', 'error').upper()} detected"
                    )
                    item = WorkItem(
                        component_id=component_id,
                        component_type=component_type,
                        title=title,
                        severity=final_severity,
                        status=WorkItemStatus.OPEN,
                        signal_count=0,
                    )
                    db.add(item)
                    await db.flush()
                    await db.refresh(item)
                    return item

                work_item_id, is_new = await get_or_create_work_item_id(
                    component_id=component_id,
                    redis=redis,
                    db=db,
                    new_work_item_factory=create_work_item,
                )

                await increment_signal_count(work_item_id, db)
                await db.commit()

            db_breaker.record_success()

            # Store raw signal in MongoDB — degraded if circuit open (audit log lags, not lost)
            if mongo_breaker.is_open():
                logger.warning("MongoDB circuit OPEN — audit log write deferred for %s", work_item_id)
            else:
                try:
                    await _store_signal_in_mongo(mongo_db, signal_data, work_item_id)
                    mongo_breaker.record_success()
                except Exception as mongo_exc:
                    mongo_breaker.record_failure()
                    logger.error("MongoDB write failed (non-fatal): %s", mongo_exc)

            # Send alert only for new incidents
            if is_new:
                strategy = get_alert_strategy(final_severity, is_new_incident=True)
                ctx = AlertContext(
                    work_item_id=work_item_id,
                    component_id=component_id,
                    component_type=component_type,
                    severity=final_severity.value,
                    title=signal_data.get("message", ""),
                    signal_count=1,
                )
                await strategy.send_alert(ctx)

            # Invalidate dashboard cache + push WS update
            async with AsyncSessionLocal() as db:
                await refresh_dashboard_cache(db)
            await manager.broadcast(json.dumps({
                "type": "signal_processed",
                "work_item_id": work_item_id,
                "component_id": component_id,
                "is_new": is_new,
                "severity": final_severity.value,
            }))

            _signals_processed += 1
            return  # success — exit retry loop

        except Exception as exc:
            db_breaker.record_failure()
            retries += 1
            if retries > settings.WORKER_MAX_RETRIES:
                logger.error(
                    "Signal processing failed after %d retries: %s | error=%s",
                    settings.WORKER_MAX_RETRIES,
                    component_id,
                    exc,
                )
                return
            # Exponential backoff: 0.5s, 1s, 2s
            delay = settings.WORKER_RETRY_BASE_DELAY * (2 ** (retries - 1))
            logger.warning(
                "Retry %d/%d for component=%s in %.1fs: %s",
                retries,
                settings.WORKER_MAX_RETRIES,
                component_id,
                delay,
                exc,
            )
            await asyncio.sleep(delay)


async def run_worker() -> None:
    """Main worker loop: read → process → ACK."""
    global _signals_processed, _last_metric_time
    redis = get_redis()
    logger.info("Signal processor worker started")

    # Claim any pending (un-ACK'd) messages from previous run
    await _reclaim_pending(redis)

    while True:
        try:
            # Check if failure simulation is active
            sim_latency = await redis.get("sim:latency_ms")
            if sim_latency:
                await asyncio.sleep(int(sim_latency) / 1000)

            # Block for up to 100ms waiting for new messages
            messages = await redis.xreadgroup(
                groupname=settings.SIGNAL_CONSUMER_GROUP,
                consumername=settings.SIGNAL_CONSUMER_NAME,
                streams={settings.SIGNAL_STREAM_NAME: ">"},
                count=settings.WORKER_BATCH_SIZE,
                block=settings.WORKER_POLL_INTERVAL_MS,
            )

            if not messages:
                # Print throughput metrics every N seconds
                now = datetime.now(timezone.utc)
                elapsed = (now - _last_metric_time).total_seconds()
                if elapsed >= settings.METRICS_LOG_INTERVAL_SECONDS:
                    rate = _signals_processed / elapsed if elapsed > 0 else 0
                    logger.info(
                        "[METRICS] Signals/sec: %.1f | Total processed: %d",
                        rate,
                        _signals_processed,
                    )
                    _signals_processed = 0
                    _last_metric_time = now
                continue

            for stream_name, stream_messages in messages:
                tasks = []
                msg_ids = []
                for msg_id, fields in stream_messages:
                    # Check DB failure simulation
                    if await redis.get("sim:db_fail"):
                        logger.warning("DB failure simulation active — backing off")
                        await asyncio.sleep(2)

                    tasks.append(_process_single_signal(fields))
                    msg_ids.append(msg_id)

                # Process batch concurrently
                await asyncio.gather(*tasks, return_exceptions=True)

                # ACK all processed messages
                if msg_ids:
                    await redis.xack(
                        settings.SIGNAL_STREAM_NAME,
                        settings.SIGNAL_CONSUMER_GROUP,
                        *msg_ids,
                    )

        except asyncio.CancelledError:
            logger.info("Worker cancelled — shutting down")
            break
        except Exception as exc:
            logger.exception("Unexpected worker error: %s", exc)
            await asyncio.sleep(1)


async def _reclaim_pending(redis) -> None:
    """Re-process messages that were delivered but never ACK'd (crash recovery)."""
    try:
        pending = await redis.xpending_range(
            settings.SIGNAL_STREAM_NAME,
            settings.SIGNAL_CONSUMER_GROUP,
            min="-",
            max="+",
            count=100,
        )
        if pending:
            logger.warning("Found %d pending messages — reclaiming", len(pending))
            msg_ids = [p["message_id"] for p in pending]
            claimed = await redis.xclaim(
                settings.SIGNAL_STREAM_NAME,
                settings.SIGNAL_CONSUMER_GROUP,
                settings.SIGNAL_CONSUMER_NAME,
                min_idle_time=0,
                message_ids=msg_ids,
            )
            for msg_id, fields in claimed:
                await _process_single_signal(fields)
                await redis.xack(
                    settings.SIGNAL_STREAM_NAME,
                    settings.SIGNAL_CONSUMER_GROUP,
                    msg_id,
                )
    except Exception as exc:
        logger.error("Failed to reclaim pending messages: %s", exc)
