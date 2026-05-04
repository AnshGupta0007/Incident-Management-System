import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security.api_key import APIKeyHeader

from ...core.config import settings
from ...core.redis_client import get_redis
from ...schemas.signal import SignalIngest, SignalResponse

router = APIRouter(prefix="/signals", tags=["Ingestion"])
logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name=settings.API_KEY_HEADER, auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if api_key != settings.INGEST_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key


async def check_rate_limit(request: Request) -> None:
    """Sliding window rate limiter using Redis sorted sets."""
    redis = get_redis()
    ip = request.client.host if request.client else "unknown"
    key = f"rate:{ip}"
    now = time.time()
    window_start = now - settings.RATE_LIMIT_WINDOW_SECONDS

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, "-inf", window_start)
    pipe.zadd(key, {str(now): now})
    pipe.zcard(key)
    pipe.expire(key, settings.RATE_LIMIT_WINDOW_SECONDS)
    results = await pipe.execute()

    request_count = results[2]
    if request_count > settings.RATE_LIMIT_REQUESTS:
        logger.warning("Rate limit exceeded for IP: %s (%d req/min)", ip, request_count)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "limit": settings.RATE_LIMIT_REQUESTS,
                "window_seconds": settings.RATE_LIMIT_WINDOW_SECONDS,
                "retry_after": settings.RATE_LIMIT_WINDOW_SECONDS,
            },
        )


@router.post(
    "",
    response_model=SignalResponse,
    status_code=202,
    summary="Ingest a signal",
    description="Non-blocking signal ingestion. Returns 202 immediately after queuing to Redis Stream.",
)
async def ingest_signal(
    signal: SignalIngest,
    request: Request,
    _: str = Depends(verify_api_key),
) -> SignalResponse:
    await check_rate_limit(request)

    redis = get_redis()

    # Prepare stream payload (Redis streams only accept string values)
    stream_data = {
        "component_id": signal.component_id,
        "component_type": signal.component_type.value,
        "signal_type": signal.signal_type,
        "severity": signal.severity.value,
        "message": signal.message,
        "payload": json.dumps(signal.payload),
        "timestamp": signal.timestamp.isoformat(),
        "source_host": signal.source_host or "",
    }

    # XADD with MAXLEN to enforce backpressure cap on the stream
    stream_id = await redis.xadd(
        settings.SIGNAL_STREAM_NAME,
        stream_data,
        maxlen=settings.STREAM_MAX_LEN,
        approximate=True,  # ~ prefix: amortized trimming is faster
    )

    logger.debug("Signal queued: stream_id=%s component=%s", stream_id, signal.component_id)

    return SignalResponse(stream_id=stream_id)


@router.post(
    "/batch",
    status_code=202,
    summary="Batch signal ingestion",
    description="Ingest up to 500 signals in a single request using a pipeline.",
)
async def ingest_batch(
    signals: list[SignalIngest],
    request: Request,
    _: str = Depends(verify_api_key),
) -> dict:
    if len(signals) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 signals per batch")

    await check_rate_limit(request)
    redis = get_redis()

    pipe = redis.pipeline()
    for signal in signals:
        stream_data = {
            "component_id": signal.component_id,
            "component_type": signal.component_type.value,
            "signal_type": signal.signal_type,
            "severity": signal.severity.value,
            "message": signal.message,
            "payload": json.dumps(signal.payload),
            "timestamp": signal.timestamp.isoformat(),
            "source_host": signal.source_host or "",
        }
        pipe.xadd(
            settings.SIGNAL_STREAM_NAME,
            stream_data,
            maxlen=settings.STREAM_MAX_LEN,
            approximate=True,
        )

    await pipe.execute()

    return {"accepted": True, "count": len(signals), "message": f"{len(signals)} signals queued"}
