from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from .config import settings
import logging

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(
            settings.MONGO_URI,
            maxPoolSize=50,
            minPoolSize=5,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
    return _client


def get_mongo_db() -> AsyncIOMotorDatabase:
    return get_mongo_client()[settings.MONGO_DB]


async def init_mongo():
    db = get_mongo_db()
    await db.signals.create_index("component_id")
    await db.signals.create_index("work_item_id")
    await db.signals.create_index([("component_id", 1), ("timestamp", -1)])
    # TTL index with explicit name — keeps raw signals 30 days then auto-deletes.
    # Named separately so it never conflicts with a plain timestamp index.
    await db.signals.create_index(
        "timestamp",
        expireAfterSeconds=2_592_000,
        name="timestamp_ttl",
    )
    logger.info("MongoDB indexes created")


async def close_mongo():
    global _client
    if _client:
        _client.close()
        _client = None
    logger.info("MongoDB connection closed")
