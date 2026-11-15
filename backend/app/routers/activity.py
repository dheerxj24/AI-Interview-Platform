from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..db import get_db
from ..llm import LLMError, complete, llm_configured, parse_json_object
from ..models import CodeSnapshot, InterviewSession, Problem, Run, Scorecard, SessionEvent
from ..realtime import manager
from ..schemas import CopilotOut, EventIn, EventOut, ProblemOut, RunCreate, RunOut, ScorecardIn, ScorecardOut, SnapshotIn
from ..tasks import run_submission

router = APIRouter(prefix="/sessions", tags=["activity"])


def _session_or_404(db: Session, session_id: int) -> InterviewSession:
    interview = db.get(InterviewSession, session_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return interview


def _latest_code(db: Session, session_id: int) -> str:
    snapshot = db.scalars(
        select(CodeSnapshot)
        .where(CodeSnapshot.session_id == session_id)
        .order_by(CodeSnapshot.id.desc())
        .limit(1)
    ).first()
    return snapshot.code if snapshot else ""


@router.get("/{session_id}/problem", response_model=ProblemOut, dependencies=[Depends(require_roles("candidate", "interviewer"))])
def session_problem(session_id: int, db: Session = Depends(get_db)) -> Problem:
    interview = _session_or_404(db, session_id)
    problem = db.get(Problem, interview.problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem


@router.get("/{session_id}/feedback", dependencies=[Depends(require_roles("candidate", "interviewer"))])
def candidate_feedback(session_id: int, db: Session = Depends(get_db)) -> dict:
    """Scores for the candidate, released only after the session has ended. Notes stay private."""
    interview = _session_or_404(db, session_id)
    card = db.scalar(select(Scorecard).where(Scorecard.session_id == session_id))
    released = interview.status == "ended" and card is not None
    return {
        "status": interview.status,
        "correctness": card.correctness if released else None,
        "communication": card.communication if released else None,
    }


@router.post("/{session_id}/events", response_model=EventOut, status_code=201, dependencies=[Depends(require_roles("candidate"))])
def record_event(session_id: int, body: EventIn, db: Session = Depends(get_db)) -> SessionEvent:
    _session_or_404(db, session_id)
    event = SessionEvent(session_id=session_id, kind=body.kind, detail=body.detail)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("/{session_id}/snapshot", dependencies=[Depends(require_roles("candidate", "interviewer"))])
def get_latest_snapshot(session_id: int, db: Session = Depends(get_db)) -> dict:
    _session_or_404(db, session_id)
    return {"code": _latest_code(db, session_id)}


@router.put("/{session_id}/snapshot", dependencies=[Depends(require_roles("candidate", "interviewer"))])
async def save_snapshot(session_id: int, payload: SnapshotIn, db: Session = Depends(get_db)) -> dict:
    _session_or_404(db, session_id)
    snapshot = CodeSnapshot(session_id=session_id, code=payload.code)
    db.add(snapshot)
    db.commit()
    await manager.broadcast(session_id, {"type": "snapshot", "code": payload.code})
    return {"saved_at": snapshot.saved_at.isoformat()}


@router.post("/{session_id}/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_roles("candidate", "interviewer"))])
def create_run(session_id: int, payload: RunCreate, db: Session = Depends(get_db)) -> Run:
    _session_or_404(db, session_id)
    code = payload.code if payload.code is not None else _latest_code(db, session_id)
    run = Run(session_id=session_id, code=code, kind=payload.kind)
    db.add(run)
    db.commit()
    db.refresh(run)
    run_submission.delay(run.id)
    db.refresh(run)
    return run


@router.get("/{session_id}/runs", response_model=list[RunOut], dependencies=[Depends(require_roles("candidate", "interviewer"))])
def list_runs(session_id: int, db: Session = Depends(get_db)) -> list[Run]:
    _session_or_404(db, session_id)
    return list(db.scalars(select(Run).where(Run.session_id == session_id).order_by(Run.id)))


@router.get("/{session_id}/runs/{run_id}", response_model=RunOut, dependencies=[Depends(require_roles("candidate", "interviewer"))])
def get_run(session_id: int, run_id: int, db: Session = Depends(get_db)) -> Run:
    run = db.get(Run, run_id)
    if run is None or run.session_id != session_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.put("/{session_id}/scorecard", response_model=ScorecardOut, dependencies=[Depends(require_roles("interviewer"))])
def upsert_scorecard(session_id: int, payload: ScorecardIn, db: Session = Depends(get_db)) -> Scorecard:
    _session_or_404(db, session_id)
    card = db.scalar(select(Scorecard).where(Scorecard.session_id == session_id))
    if card is None:
        card = Scorecard(session_id=session_id, correctness=payload.correctness, communication=payload.communication)
        db.add(card)
    card.correctness = payload.correctness
    card.communication = payload.communication
    card.notes = payload.notes
    db.commit()
    db.refresh(card)
    return card


@router.get("/{session_id}/scorecard", response_model=ScorecardOut, dependencies=[Depends(require_roles("interviewer"))])
def get_scorecard(session_id: int, db: Session = Depends(get_db)) -> Scorecard:
    card = db.scalar(select(Scorecard).where(Scorecard.session_id == session_id))
    if card is None:
        raise HTTPException(status_code=404, detail="No scorecard yet")
    return card


@router.get("/{session_id}/summary", dependencies=[Depends(require_roles("interviewer"))])
def session_summary(session_id: int, db: Session = Depends(get_db)) -> dict:
    interview = _session_or_404(db, session_id)
    problem = db.get(Problem, interview.problem_id)
    best_full = db.scalars(
        select(Run)
        .where(Run.session_id == session_id, Run.kind == "full", Run.status == "done")
        .order_by(Run.passed_count.desc(), Run.id.desc())
        .limit(1)
    ).first()
    card = db.scalar(select(Scorecard).where(Scorecard.session_id == session_id))
    run_count = len(list(db.scalars(select(Run.id).where(Run.session_id == session_id))))
    events = list(
        db.scalars(
            select(SessionEvent).where(SessionEvent.session_id == session_id).order_by(SessionEvent.id)
        )
    )
    return {
        "session": {
            "id": interview.id,
            "candidate_name": interview.candidate_name,
            "interviewer_name": interview.interviewer_name,
            "status": interview.status,
            "started_at": interview.started_at,
            "ended_at": interview.ended_at,
        },
        "problem": {"id": problem.id, "title": problem.title, "difficulty": problem.difficulty},
        "code": _latest_code(db, session_id),
        "run_count": run_count,
        "best_full_run": (
            {"passed": best_full.passed_count, "total": best_full.total_count} if best_full else None
        ),
        "events": [{"kind": e.kind, "detail": e.detail, "at": e.created_at} for e in events],
        "scorecard": (
            {
                "correctness": card.correctness,
                "communication": card.communication,
                "notes": card.notes,
            }
            if card
            else None
        ),
    }


def _numbered_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in ".)":
            lines.append(stripped)
    return lines


@router.post("/{session_id}/copilot", response_model=CopilotOut, dependencies=[Depends(require_roles("interviewer"))])
def copilot(session_id: int, db: Session = Depends(get_db)) -> dict:
    interview = _session_or_404(db, session_id)
    if not llm_configured():
        raise HTTPException(status_code=503, detail="AI co-pilot is not configured")
    code = _latest_code(db, session_id)
    if not code.strip():
        raise HTTPException(status_code=400, detail="No code to review yet")
    problem = db.get(Problem, interview.problem_id)

    prompt = (
        "You are helping an interviewer. The candidate was given this problem:\n"
        f"{problem.title}: {problem.prompt}\n\n"
        "Here is the candidate's Python code:\n```python\n"
        f"{code}\n```\n\n"
        "Write exactly three short follow-up questions. Each question must point to a specific part of "
        "the code and probe whether the candidate understands it. Do not reveal the answer. "
        "Number them 1, 2 and 3 and write nothing else."
    )
    try:
        text = complete(prompt, max_tokens=400)
        questions = _numbered_lines(text)
        if len(questions) < 3:
            retry = complete(
                prompt + "\n\nYour previous reply did not contain three numbered questions. Try again.",
                max_tokens=400,
            )
            if len(_numbered_lines(retry)) > len(questions):
                text = retry
                questions = _numbered_lines(retry)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    suggestions = "\n".join(questions[:3]) if questions else text.strip()
    return {"suggestions": suggestions}


@router.post("/{session_id}/ai-scorecard", response_model=ScorecardIn, dependencies=[Depends(require_roles("interviewer"))])
def ai_scorecard(session_id: int, db: Session = Depends(get_db)) -> ScorecardIn:
    """Drafts scores for the interviewer to review. Nothing is saved until they submit the form."""
    interview = _session_or_404(db, session_id)
    if not llm_configured():
        raise HTTPException(status_code=503, detail="AI co-pilot is not configured")
    code = _latest_code(db, session_id)
    if not code.strip():
        raise HTTPException(status_code=400, detail="No code to score yet")
    problem = db.get(Problem, interview.problem_id)
    best_full = db.scalars(
        select(Run)
        .where(Run.session_id == session_id, Run.kind == "full", Run.status == "done")
        .order_by(Run.passed_count.desc(), Run.id.desc())
        .limit(1)
    ).first()
    event_counts = Counter(
        e.kind for e in db.scalars(select(SessionEvent).where(SessionEvent.session_id == session_id))
    )
    run_line = (
        f"{best_full.passed_count} of {best_full.total_count} tests passed in the best full run"
        if best_full
        else "no full test run yet"
    )
    prompt = (
        "You are helping an interviewer score a coding interview. Be fair and specific.\n"
        f"Problem: {problem.title}: {problem.prompt}\n"
        f"Test results: {run_line}.\n"
        f"Integrity events: tab_hidden={event_counts['tab_hidden']}, "
        f"window_blur={event_counts['window_blur']}, paste={event_counts['paste']}.\n\n"
        "Candidate's final Python code:\n```python\n" + code + "\n```\n\n"
        "Return only a JSON object with these keys: "
        '"correctness" (integer 1-5: how correct and complete the solution is), '
        '"communication" (integer 1-5: estimated from code clarity and naming, since no conversation is recorded), '
        '"notes" (2-4 sentences explaining the scores; mention integrity events only if they were recorded).'
    )
    try:
        data = parse_json_object(complete(prompt, max_tokens=500))
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    try:
        return ScorecardIn(**{k: data[k] for k in ("correctness", "communication", "notes") if k in data})
    except (ValidationError, TypeError):
        raise HTTPException(status_code=502, detail="AI draft was not in the expected format")
