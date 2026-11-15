import asyncio

from app.realtime import ConnectionManager, decode_envelope, encode_envelope


class FakeSocket:
    def __init__(self):
        self.sent = []

    async def send(self, frame):
        self.sent.append(frame)


def test_text_envelope_round_trip():
    raw = encode_envelope({"type": "websocket.send", "text": "hi"}, origin="c1")
    origin, frame = decode_envelope(raw)
    assert origin == "c1"
    assert frame == {"type": "websocket.send", "text": "hi"}


def test_binary_envelope_round_trip():
    raw = encode_envelope({"type": "websocket.send", "bytes": b"\x00\x01data"}, origin=None)
    origin, frame = decode_envelope(raw)
    assert origin is None
    assert frame["bytes"] == b"\x00\x01data"


def test_redis_message_reaches_room_except_origin():
    manager = ConnectionManager()
    sender, listener = FakeSocket(), FakeSocket()
    manager.rooms[7] = {"sender": sender, "listener": listener}
    envelope = encode_envelope({"type": "websocket.send", "text": "x = 1"}, origin="sender")

    asyncio.run(manager.handle_envelope(7, envelope))

    assert sender.sent == []
    assert listener.sent == [{"type": "websocket.send", "text": "x = 1"}]


def test_memory_mode_relays_directly():
    manager = ConnectionManager()
    sender, listener = FakeSocket(), FakeSocket()
    manager.rooms[3] = {"a": sender, "b": listener}
    asyncio.run(manager.relay(3, {"type": "websocket.send", "text": "ping"}, origin="a"))
    assert listener.sent and not sender.sent
    assert listener.sent[0]["text"] == "ping"
