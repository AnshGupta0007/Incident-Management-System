import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from ...core.circuit_breaker import db_breaker, mongo_breaker, redis_breaker
from ...core.database import AsyncSessionLocal, engine
from ...core.mongodb import get_mongo_db
from ...core.redis_client import get_redis
from ...core.config import settings

router = APIRouter(tags=["Health"])
logger = logging.getLogger(__name__)


@router.get("/health", summary="Deep health check for all services")
async def health_check() -> dict:
    checks: dict[str, dict] = {}

    # PostgreSQL — connectivity + pool stats
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        pool = engine.pool
        pool_stats = {
            "size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "checked_in": pool.checkedin(),
        }
        checks["postgres"] = {
            "status": "ok",
            "pool": pool_stats,
            "circuit_breaker": db_breaker.status(),
        }
    except Exception as exc:
        checks["postgres"] = {
            "status": "degraded",
            "error": str(exc),
            "circuit_breaker": db_breaker.status(),
        }

    # Redis — ping + stream backlog
    try:
        redis = get_redis()
        await redis.ping()
        stream_len = await redis.xlen(settings.SIGNAL_STREAM_NAME)
        checks["redis"] = {
            "status": "ok",
            "stream_backlog": stream_len,
            "circuit_breaker": redis_breaker.status(),
        }
    except Exception as exc:
        checks["redis"] = {
            "status": "degraded",
            "error": str(exc),
            "circuit_breaker": redis_breaker.status(),
        }

    # MongoDB — signal count
    try:
        mongo_db = get_mongo_db()
        count = await mongo_db.signals.count_documents({})
        checks["mongodb"] = {
            "status": "ok",
            "total_signals": count,
            "circuit_breaker": mongo_breaker.status(),
        }
    except Exception as exc:
        checks["mongodb"] = {
            "status": "degraded",
            "error": str(exc),
            "circuit_breaker": mongo_breaker.status(),
        }

    overall = "healthy" if all(v["status"] == "ok" for v in checks.values()) else "degraded"

    return {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": checks,
    }


@router.get("/ready", summary="Readiness probe (K8s)")
async def readiness() -> dict:
    return {"ready": True}


@router.get("/live", summary="Liveness probe (K8s)")
async def liveness() -> dict:
    return {"alive": True}
