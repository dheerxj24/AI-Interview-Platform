import asyncio
import base64
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session as DBSession

from .auth import resolve_role
from .config import settings
from .db import get_db

MAX_FRAME_BYTES = 1_000_000
logger = logging.getLogger("realtime")


def encode_envelope(frame: dict, origin: Optional[str]) -> str:
    """Wrap a WebSocket frame so it can travel through Redis. Binary data is base64-encoded."""
    if frame.get("bytes") is not None:
        body = {"bytes": base64.b64encode(frame["bytes"]).decode("ascii")}
    else:
        body = {"text": frame.get("text")}
    return json.dumps({"origin": origin, **body})


def decode_envelope(data: str) -> tuple[Optional[str], dict]:
    envelope = json.loads(data)
    if envelope.get("bytes") is not None:
        frame = {"type": "websocket.send", "bytes": base64.b64decode(envelope["bytes"])}
    else:
        frame = {"type": "websocket.send", "text": envelope.get("text") or ""}
    return envelope.get("origin"), frame


class ConnectionManager:
    """Rooms of WebSocket connections keyed by session id."""

    def __init__(self) -> None:
        self.rooms: dict[int, dict[str, WebSocket]] = {}
        self.redis = None
        self._listener: Optional[asyncio.Task] = None

    async def connect(self, session_id: int, websocket: WebSocket) -> str:
        await websocket.accept()
        conn_id = uuid.uuid4().hex
        self.rooms.setdefault(session_id, {})[conn_id] = websocket
        return conn_id

    def disconnect(self, session_id: int, conn_id: str) -> None:
        self.rooms.get(session_id, {}).pop(conn_id, None)

    async def deliver_local(self, session_id: int, frame: dict, exclude: Optional[str]) -> None:
        for conn_id, socket in list(self.rooms.get(session_id, {}).items()):
            if conn_id == exclude:
                continue
            try:
                await socket.send(frame)
            except Exception:
                self.disconnect(session_id, conn_id)

    async def relay(self, session_id: int, frame: dict, origin: Optional[str]) -> None:
        if self.redis is None:
            await self.deliver_local(session_id, frame, exclude=origin)
        else:
            await self.redis.publish(f"session:{session_id}", encode_envelope(frame, origin))

    async def broadcast(self, session_id: int, message: dict) -> None:
        # Used by HTTP handlers: every connected client gets the message.
        await self.relay(session_id, {"type": "websocket.send", "text": json.dumps(message)}, origin=None)

    async def handle_envelope(self, session_id: int, data: str) -> None:
        origin, frame = decode_envelope(data)
        await self.deliver_local(session_id, frame, exclude=origin)

    async def _listen(self) -> None:
        # Poll explicitly and retry on failure, so a dropped Redis connection doesn't silently stop relaying.
        while True:
            try:
                pubsub = self.redis.pubsub()
                await pubsub.psubscribe("session:*")
                while True:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message is None or message.get("type") != "pmessage":
                        continue
                    # Redis returns bytes unless decode_responses is set.
                    channel = message["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode()
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    session_id = int(channel.split(":", 1)[1])
                    await self.handle_envelope(session_id, data)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Realtime listener failed; retrying in 1s")
                await asyncio.sleep(1)

    async def start(self) -> None:
        from redis.asyncio import Redis

        self.redis = Redis.from_url(settings.redis_url)
        self._listener = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._listener is not None:
            self._listener.cancel()
        if self.redis is not None:
            await self.redis.aclose()
        self.redis = None


manager = ConnectionManager()
router = APIRouter(tags=["realtime"])


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(
    websocket: WebSocket,
    session_id: int,
    token: str = Query(default=""),
    db: DBSession = Depends(get_db),
) -> None:
    if resolve_role(db, session_id, token) is None:
        await websocket.close(code=4401)
        return
    conn_id = await manager.connect(session_id, websocket)
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                frame = {"type": "websocket.send", "bytes": message["bytes"]}
            elif message.get("text") is not None:
                frame = {"type": "websocket.send", "text": message["text"]}
            else:
                continue
            size = len(frame.get("bytes") or frame.get("text") or "")
            if size > MAX_FRAME_BYTES:
                continue
            await manager.relay(session_id, frame, origin=conn_id)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(session_id, conn_id)
