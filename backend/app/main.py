import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from .core.config import settings
from .core.database import close_db, init_db
from .core.mongodb import close_mongo, init_mongo
from .core.redis_client import close_redis, init_redis
from .api.routes import health, incidents, ingestion, websocket, simulate, metrics
from .workers.signal_processor import run_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

_worker_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("Starting %s", settings.APP_NAME)
    await init_redis()
    await init_db()
    await init_mongo()

    global _worker_task
    _worker_task = asyncio.create_task(run_worker(), name="signal-processor")
    logger.info("Signal processor worker started")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Shutting down gracefully...")
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await asyncio.wait_for(_worker_task, timeout=10)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    await close_redis()
    await close_mongo()
    await close_db()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Production-grade Incident Management System with async processing, deduplication, and real-time dashboard.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_timing(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Response-Time-Ms"] = f"{duration_ms:.1f}"
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )


# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(health.router)
app.include_router(websocket.router)
app.include_router(ingestion.router, prefix=settings.API_V1_PREFIX)
app.include_router(incidents.router, prefix=settings.API_V1_PREFIX)
app.include_router(simulate.router, prefix=settings.API_V1_PREFIX)
app.include_router(metrics.router, prefix=settings.API_V1_PREFIX)


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": settings.APP_NAME,
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
