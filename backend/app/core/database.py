from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event
from .config import settings
import logging

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.POSTGRES_DSN,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,       # validates connection before use
    pool_recycle=3600,        # recycle connections every hour
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("PostgreSQL tables created")


async def close_db():
    await engine.dispose()
    logger.info("PostgreSQL engine disposed")
