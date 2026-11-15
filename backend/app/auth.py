"""Access control. Session tokens are per role; the admin token opens any session as the interviewer."""
import hashlib
import hmac
import secrets
from typing import Callable

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import SessionToken

ROLES = ("candidate", "interviewer")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_tokens(db: Session, session_id: int) -> dict[str, str]:
    """Create one token per role. The caller commits the session."""
    issued: dict[str, str] = {}
    for role in ROLES:
        token = secrets.token_urlsafe(24)
        db.add(SessionToken(session_id=session_id, role=role, token_hash=_hash(token)))
        issued[role] = token
    return issued


def role_for_token(db: Session, session_id: int, token: str | None) -> str | None:
    if not token:
        return None
    return db.scalar(
        select(SessionToken.role).where(
            SessionToken.session_id == session_id,
            SessionToken.token_hash == _hash(token),
        )
    )


def is_admin(token: str | None) -> bool:
    return bool(settings.admin_token) and bool(token) and hmac.compare_digest(token, settings.admin_token)


def resolve_role(db: Session, session_id: int, token: str | None) -> str | None:
    """Role for a single token, used by the WebSocket which takes one token in the URL."""
    if is_admin(token):
        return "interviewer"
    return role_for_token(db, session_id, token)


def require_roles(*allowed: str) -> Callable:
    """A session token must belong to this session. The admin token counts as the interviewer."""

    def check(
        session_id: int,
        x_session_token: str | None = Header(default=None),
        x_admin_token: str | None = Header(default=None),
        db: Session = Depends(get_db),
    ) -> str:
        role = role_for_token(db, session_id, x_session_token)
        if role is None and is_admin(x_admin_token):
            role = "interviewer"
        if role is None:
            raise HTTPException(status_code=401, detail="Missing or invalid session token")
        if role not in allowed:
            raise HTTPException(status_code=403, detail="This session token cannot do that")
        return role

    return check


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.admin_token:
        raise HTTPException(status_code=503, detail="Admin access is not configured")
    if not is_admin(x_admin_token):
        raise HTTPException(status_code=401, detail="Admin token required")
