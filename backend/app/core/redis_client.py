import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool
from .config import settings
import logging

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_client: aioredis.Redis | None = None


def get_redis_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=100,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True,
        )
    return _pool


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.Redis(connection_pool=get_redis_pool())
    return _client


async def init_redis():
    r = get_redis()
    await r.ping()
    # Ensure consumer group exists for the signal stream
    try:
        await r.xgroup_create(
            settings.SIGNAL_STREAM_NAME,
            settings.SIGNAL_CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )
        logger.info("Redis stream consumer group created")
    except aioredis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.info("Redis stream consumer group already exists")
        else:
            raise
    logger.info("Redis initialized")


async def close_redis():
    global _client, _pool
    if _client:
        await _client.aclose()
        _client = None
    if _pool:
        await _pool.aclose()
        _pool = None
    logger.info("Redis connection closed")
