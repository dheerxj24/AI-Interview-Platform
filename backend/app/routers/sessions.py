from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import issue_tokens, require_admin, require_roles
from ..db import get_db
from ..models import InterviewSession, Problem
from ..schemas import SessionCreate, SessionCreated, SessionOut, SessionUpdate

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _get_session_or_404(db: Session, session_id: int) -> InterviewSession:
    interview = db.get(InterviewSession, session_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return interview


@router.post("", response_model=SessionCreated, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_session(payload: SessionCreate, db: Session = Depends(get_db)) -> InterviewSession:
    if db.get(Problem, payload.problem_id) is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    interview = InterviewSession(**payload.model_dump())
    db.add(interview)
    db.flush()
    tokens = issue_tokens(db, interview.id)
    db.commit()
    db.refresh(interview)
    return {
        **SessionOut.model_validate(interview).model_dump(),
        "candidate_token": tokens["candidate"],
        "interviewer_token": tokens["interviewer"],
    }


@router.get("", response_model=list[SessionOut], dependencies=[Depends(require_admin)])
def list_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[InterviewSession]:
    query = select(InterviewSession).order_by(InterviewSession.id).limit(limit).offset(offset)
    return list(db.scalars(query))


@router.get("/{session_id}", response_model=SessionOut, dependencies=[Depends(require_roles("candidate", "interviewer"))])
def get_session(session_id: int, db: Session = Depends(get_db)) -> InterviewSession:
    return _get_session_or_404(db, session_id)


@router.patch("/{session_id}", response_model=SessionOut, dependencies=[Depends(require_roles("interviewer"))])
def update_session(
    session_id: int, payload: SessionUpdate, db: Session = Depends(get_db)
) -> InterviewSession:
    interview = _get_session_or_404(db, session_id)
    if payload.status is not None:
        now = datetime.now(timezone.utc)
        interview.status = payload.status
        if payload.status == "live" and interview.started_at is None:
            interview.started_at = now
        if payload.status == "ended":
            interview.ended_at = now
    db.commit()
    db.refresh(interview)
    return interview
