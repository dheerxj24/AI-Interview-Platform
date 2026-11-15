from collections.abc import Iterator

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app import tasks as tasks_module
from app.config import settings
from app.db import Base, get_db
from app.main import app


class AuthedClient(TestClient):
    """Adds the interviewer token to session requests, so tests that use the owner's view keep working."""

    def __init__(self, app):
        super().__init__(app)
        self.tokens: dict[int, dict] = {}

    def request(self, method, url, **kwargs):
        if url == "/sessions" or url.startswith("/problems"):
            headers = dict(kwargs.pop("headers", None) or {})
            headers.setdefault("X-Admin-Token", "test-admin")
            kwargs["headers"] = headers
        match = re.match(r"^/sessions/(\d+)", url)
        if match and int(match.group(1)) in self.tokens:
            headers = dict(kwargs.pop("headers", None) or {})
            headers.setdefault("X-Session-Token", self.tokens[int(match.group(1))]["interviewer_token"])
            kwargs["headers"] = headers
        response = super().request(method, url, **kwargs)
        if method == "POST" and url == "/sessions" and response.status_code == 201:
            body = response.json()
            self.tokens[body["id"]] = body
        return response

    def websocket_connect(self, url, **kwargs):
        match = re.match(r"^/ws/sessions/(\d+)", url)
        if match and "?" not in url and int(match.group(1)) in self.tokens:
            url += f"?token={self.tokens[int(match.group(1))]['interviewer_token']}"
        return super().websocket_connect(url, **kwargs)


@pytest.fixture
def client(monkeypatch) -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(settings, "admin_token", "test-admin")
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db() -> Iterator[Session]:
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Background tasks use the test database, and run inline instead of through Redis.
    monkeypatch.setattr(tasks_module, "SessionLocal", TestingSession)
    tasks_module.celery_app.conf.task_always_eager = True

    # No `with` block: skips lifespan so tests never touch dev.db.
    yield AuthedClient(app)

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
