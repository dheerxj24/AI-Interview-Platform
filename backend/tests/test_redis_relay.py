import asyncio

import pytest

fakeredis = pytest.importorskip("fakeredis")
import redis.asyncio as aredis  # noqa: E402

from app import realtime  # noqa: E402


class FakeSocket:
    def __init__(self):
        self.sent = []

    async def send(self, frame):
        self.sent.append(frame)


def test_redis_relay_reaches_others_but_not_sender(monkeypatch):
    # In-process fake Redis server, so no real Redis is needed.
    server = fakeredis.FakeServer()
    monkeypatch.setattr(
        aredis.Redis,
        "from_url",
        classmethod(lambda cls, url, **kw: fakeredis.FakeAsyncRedis(server=server, decode_responses=False)),
    )

    async def scenario():
        manager = realtime.ConnectionManager()
        await manager.start()
        await asyncio.sleep(0.2)
        sender, listener = FakeSocket(), FakeSocket()
        manager.rooms[2] = {"sender": sender, "listener": listener}
        await manager.relay(2, {"type": "websocket.send", "text": "hello"}, origin="sender")
        await manager.relay(2, {"type": "websocket.send", "bytes": b"\x00doc"}, origin="sender")
        await asyncio.sleep(0.5)
        await manager.stop()
        return sender, listener

    sender, listener = asyncio.run(scenario())
    assert sender.sent == []
    assert listener.sent == [
        {"type": "websocket.send", "text": "hello"},
        {"type": "websocket.send", "bytes": b"\x00doc"},
    ]
