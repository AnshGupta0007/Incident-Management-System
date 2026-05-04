import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Thread-safe WebSocket connection registry."""

    def __init__(self):
        self._active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._active.append(ws)
        logger.debug("WebSocket connected. Total: %d", len(self._active))

    def disconnect(self, ws: WebSocket) -> None:
        self._active.remove(ws)
        logger.debug("WebSocket disconnected. Total: %d", len(self._active))

    async def broadcast(self, message: str) -> None:
        disconnected = []
        for ws in self._active:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self._active.remove(ws)

    async def send_personal(self, message: str, ws: WebSocket) -> None:
        try:
            await ws.send_text(message)
        except Exception:
            self.disconnect(ws)


manager = ConnectionManager()
