"""
Circuit Breaker pattern for external service calls.

States:
  CLOSED   → healthy, requests pass through normally
  OPEN     → unhealthy, requests rejected immediately (fail-fast)
  HALF_OPEN → probing: one request allowed through to test recovery

Thresholds:
  db_breaker    — 5 failures in a row → OPEN for 30s
  mongo_breaker — 5 failures in a row → OPEN for 30s
  redis_breaker — 3 failures in a row → OPEN for 10s
"""

import logging
import time
from enum import Enum
from typing import Awaitable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - (self._opened_at or 0) >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info("CircuitBreaker[%s] → HALF_OPEN (probing recovery)", self.name)
        return self._state

    def record_success(self) -> None:
        if self._state != CircuitState.CLOSED:
            logger.info("CircuitBreaker[%s] → CLOSED (service recovered)", self.name)
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold and self._state == CircuitState.CLOSED:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "CircuitBreaker[%s] → OPEN after %d consecutive failures",
                self.name,
                self._failures,
            )

    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    def status(self) -> dict:
        return {
            "state": self.state.value,
            "consecutive_failures": self._failures,
            "threshold": self.failure_threshold,
        }

    async def call(self, coro: Awaitable[T]) -> T:
        if self.is_open():
            raise RuntimeError(f"Circuit breaker '{self.name}' is OPEN — service unavailable")
        try:
            result = await coro
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


# Module-level singletons — shared across worker and health endpoint
db_breaker = CircuitBreaker("postgresql", failure_threshold=5, recovery_timeout=30.0)
mongo_breaker = CircuitBreaker("mongodb", failure_threshold=5, recovery_timeout=30.0)
redis_breaker = CircuitBreaker("redis", failure_threshold=3, recovery_timeout=10.0)
