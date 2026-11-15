import json

from celery import Celery
from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .executor import execute
from .judge import judge
from .models import InterviewSession, Run, TestCase

# The result backend lets the API wait for a task's result (used by the problem draft check).
celery_app = Celery("interview", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_always_eager = settings.celery_eager
celery_app.conf.task_eager_propagates = True


@celery_app.task(name="run_reference")
def run_reference(code: str, inputs: list[str]) -> list[dict]:
    """Run an AI-drafted reference solution in the worker's sandbox, one outcome per input."""
    return [execute(code, stdin_text) for stdin_text in inputs]


@celery_app.task(name="run_submission")
def run_submission(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if run is None:
            return
        interview = db.get(InterviewSession, run.session_id)
        tests = list(db.scalars(
            select(TestCase).where(TestCase.problem_id == interview.problem_id).order_by(TestCase.id)
        ))
        if run.kind == "visible":
            tests = [t for t in tests if not t.is_hidden]

        outcome = judge(run.code, tests, include_details=(run.kind == "visible"))
        run.status = "done"
        run.passed_count = outcome["passed"]
        run.total_count = outcome["total"]
        run.runtime_ms = outcome["runtime_ms"]
        run.output = json.dumps(outcome["results"]) if run.kind == "visible" else ""
        db.commit()
    except Exception as exc:  # record the failure on the run instead of losing it
        db.rollback()
        run = db.get(Run, run_id)
        if run is not None:
            run.status = "error"
            run.error = str(exc)[:500]
            db.commit()
    finally:
        db.close()
