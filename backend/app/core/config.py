from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Incident Management System"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # PostgreSQL
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "ims_user"
    POSTGRES_PASSWORD: str = "ims_password"
    POSTGRES_DB: str = "ims_db"

    @property
    def POSTGRES_DSN(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def POSTGRES_DSN_SYNC(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # MongoDB
    MONGO_HOST: str = "mongodb"
    MONGO_PORT: int = 27017
    MONGO_DB: str = "ims_signals"

    @property
    def MONGO_URI(self) -> str:
        return f"mongodb://{self.MONGO_HOST}:{self.MONGO_PORT}"

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # Signal Stream
    SIGNAL_STREAM_NAME: str = "signals:stream"
    SIGNAL_CONSUMER_GROUP: str = "signal_processors"
    SIGNAL_CONSUMER_NAME: str = "worker-1"
    STREAM_MAX_LEN: int = 100_000  # cap stream to 100k messages

    # Deduplication window (seconds)
    DEDUP_WINDOW_SECONDS: int = 10

    # Rate limiting (requests per minute per IP)
    RATE_LIMIT_REQUESTS: int = 600
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Worker settings
    WORKER_BATCH_SIZE: int = 50
    WORKER_POLL_INTERVAL_MS: int = 100
    WORKER_MAX_RETRIES: int = 3
    WORKER_RETRY_BASE_DELAY: float = 0.5  # seconds

    # Observability
    METRICS_LOG_INTERVAL_SECONDS: int = 5

    # Security
    SECRET_KEY: str = "super-secret-key-change-in-production"
    API_KEY_HEADER: str = "X-API-Key"
    INGEST_API_KEY: str = "ims-ingest-key-2024"

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
