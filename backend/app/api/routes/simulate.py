"""
Failure Simulation Engine.

Allows controlled injection of failure modes for testing backpressure,
retry logic, and graceful degradation without actually breaking infrastructure.
"""

import asyncio
import logging
import random
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...core.config import settings
from ...core.redis_client import get_redis
from ...schemas.signal import SignalIngest
from ...models.work_item import ComponentType, Severity

router = APIRouter(prefix="/simulate", tags=["Simulation"])
logger = logging.getLogger(__name__)


class SimulationConfig(BaseModel):
    duration_seconds: int = 30
    latency_ms: int = 2000


@router.post("/db-failure", summary="Simulate PostgreSQL degradation")
async def simulate_db_failure(config: SimulationConfig) -> dict:
    """Sets a Redis flag that makes the worker detect DB failure and back off."""
    redis = get_redis()
    await redis.setex("sim:db_fail", config.duration_seconds, "1")
    logger.warning(
        "DB failure simulation started for %ds", config.duration_seconds
    )
    return {
        "simulation": "db_failure",
        "active_for_seconds": config.duration_seconds,
        "message": "Worker will apply backoff. Signals continue buffering in Redis Stream.",
    }


@router.post("/latency-spike", summary="Simulate processing latency spike")
async def simulate_latency(config: SimulationConfig) -> dict:
    """Injects artificial processing delay into the worker."""
    redis = get_redis()
    await redis.setex("sim:latency_ms", config.duration_seconds, str(config.latency_ms))
    return {
        "simulation": "latency_spike",
        "latency_ms": config.latency_ms,
        "active_for_seconds": config.duration_seconds,
    }


@router.post("/burst", summary="Fire 200 signals simulating an RDBMS outage cascade")
async def simulate_burst() -> dict:
    """
    Simulates a real-world cascade:
    1. RDBMS starts throwing errors
    2. API layer starts failing
    3. Cache starts evicting due to memory pressure
    """
    import json as _json
    redis = get_redis()

    components = [
        ("RDBMS_CLUSTER_01", ComponentType.RDBMS, Severity.P0, "Connection pool exhausted"),
        ("API_GATEWAY_01", ComponentType.API, Severity.P1, "Upstream RDBMS timeout"),
        ("CACHE_CLUSTER_01", ComponentType.CACHE, Severity.P2, "Cache miss rate spike"),
        ("MCP_HOST_01", ComponentType.MCP_HOST, Severity.P1, "MCP host health check failed"),
        ("ASYNC_QUEUE_01", ComponentType.QUEUE, Severity.P2, "Consumer lag exceeded threshold"),
    ]

    count = 0
    for i in range(200):
        comp_id, comp_type, severity, msg = components[i % len(components)]
        stream_data = {
            "component_id": comp_id,
            "component_type": comp_type.value,
            "signal_type": "error",
            "severity": severity.value,
            "message": f"{msg} (burst #{i+1})",
            "payload": _json.dumps({"burst_id": i, "simulated": True}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_host": f"sim-host-{i % 5}",
        }
        await redis.xadd(
            settings.SIGNAL_STREAM_NAME,
            stream_data,
            maxlen=settings.STREAM_MAX_LEN,
            approximate=True,
        )
        count += 1

    return {
        "simulation": "burst",
        "signals_injected": count,
        "components": [c[0] for c in components],
        "message": "200 signals injected. Deduplication engine will reduce to ~5 work items.",
    }


@router.post("/reset", summary="Reset all active simulations")
async def reset_simulations() -> dict:
    redis = get_redis()
    await redis.delete("sim:db_fail", "sim:latency_ms")
    return {"message": "All simulations reset"}


@router.get("/status", summary="Check active simulations")
async def simulation_status() -> dict:
    redis = get_redis()
    db_fail = await redis.get("sim:db_fail")
    latency = await redis.get("sim:latency_ms")
    stream_len = await redis.xlen(settings.SIGNAL_STREAM_NAME)
    return {
        "db_failure_active": db_fail is not None,
        "latency_spike_ms": int(latency) if latency else None,
        "stream_backlog": stream_len,
    }
