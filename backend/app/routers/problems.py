import re

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..db import get_db
from ..llm import LLMError, complete, llm_configured, parse_json_object
from ..models import Problem, TestCase
from ..tasks import run_reference
from ..schemas import (
    ProblemCreate,
    ProblemDraftIn,
    ProblemDraftOut,
    ProblemOut,
    ProblemUpdate,
    TestCaseCreate,
    TestCaseOut,
)

router = APIRouter(prefix="/problems", tags=["problems"])


def _get_or_404(db: Session, problem_id: int) -> Problem:
    problem = db.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem


def _public_test(test: TestCase) -> dict:
    visible = not test.is_hidden
    return {
        "id": test.id,
        "is_hidden": test.is_hidden,
        "input_text": test.input_text if visible else None,
        "expected_output": test.expected_output if visible else None,
    }


@router.post("", response_model=ProblemOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_problem(payload: ProblemCreate, db: Session = Depends(get_db)) -> Problem:
    problem = Problem(**payload.model_dump())
    db.add(problem)
    db.commit()
    db.refresh(problem)
    return problem


@router.get("", response_model=list[ProblemOut], dependencies=[Depends(require_admin)])
def list_problems(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[Problem]:
    query = (
        select(Problem)
        .where(Problem.archived.is_(False))
        .order_by(Problem.id)
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(query))


@router.get("/{problem_id}", response_model=ProblemOut, dependencies=[Depends(require_admin)])
def get_problem(problem_id: int, db: Session = Depends(get_db)) -> Problem:
    return _get_or_404(db, problem_id)


@router.patch("/{problem_id}", response_model=ProblemOut, dependencies=[Depends(require_admin)])
def update_problem(problem_id: int, payload: ProblemUpdate, db: Session = Depends(get_db)) -> Problem:
    problem = _get_or_404(db, problem_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(problem, field, value)
    db.commit()
    db.refresh(problem)
    return problem


@router.delete("/{problem_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
def delete_problem(problem_id: int, db: Session = Depends(get_db)) -> Response:
    # Archive rather than delete so past interview sessions keep their problem.
    problem = _get_or_404(db, problem_id)
    problem.archived = True
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


FENCE = "```"

_TITLE_RE = re.compile(r"TITLE:\s*(.+?)\s*$", re.MULTILINE)
_PROMPT_RE = re.compile(r"PROMPT:\s*(.*?)(?=SOLUTION:)", re.DOTALL)
_CODE_RE = re.compile(FENCE + r"(?:python|py)?[ \t]*\n(.*?)" + FENCE, re.DOTALL)
_INPUT_LINE_RE = re.compile(r"^\s*-\s?(.*)$")


def parse_problem_text(text: str) -> dict:
    """Read the labelled sections of a model reply. Plain sections survive small models better than JSON with code inside."""
    title_match = _TITLE_RE.search(text)
    prompt_match = _PROMPT_RE.search(text)
    solution_at = text.find("SOLUTION:")
    code_match = _CODE_RE.search(text, solution_at) if solution_at != -1 else None
    inputs_at = text.find("INPUTS:")
    inputs = []
    if inputs_at != -1:
        for line in text[inputs_at + len("INPUTS:"):].splitlines():
            match = _INPUT_LINE_RE.match(line)
            if match:
                value = match.group(1).strip().strip("`'\"").strip()
                if value:
                    inputs.append(value.replace("\\n", "\n"))

    missing = []
    if not title_match:
        missing.append("TITLE")
    if not prompt_match or not prompt_match.group(1).strip():
        missing.append("PROMPT")
    if not code_match or not code_match.group(1).strip():
        missing.append("SOLUTION code block")
    if not inputs:
        missing.append("INPUTS list")
    if missing:
        raise LLMError("AI draft was missing " + ", ".join(missing))

    return {
        "title": title_match.group(1)[:200],
        "prompt": prompt_match.group(1).strip(),
        "reference_solution": code_match.group(1).rstrip(),
        "test_inputs": inputs[:6],
    }


def _run_reference(code: str, inputs: list[str]) -> tuple[list[dict], str | None]:
    """Run the reference solution in the worker's sandbox. Its output becomes the expected output."""
    try:
        outcomes = run_reference.delay(code, inputs).get(timeout=120)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="The sandbox did not respond. Check that the worker is running.",
        ) from exc
    tests = []
    for index, (stdin_text, outcome) in enumerate(zip(inputs, outcomes)):
        if not outcome["ok"]:
            reason = outcome["stderr"].strip()[-200:] or "no error text"
            return [], f"the solution crashed on test {index + 1}: {reason}"
        tests.append({
            "input_text": stdin_text,
            "expected_output": outcome["stdout"].strip(),
            "is_hidden": index > 0 and index == len(inputs) - 1,
        })
    return tests, None


@router.post("/ai-draft", response_model=ProblemDraftOut, dependencies=[Depends(require_admin)])
def ai_problem_draft(payload: ProblemDraftIn) -> dict:
    """Drafts a problem. The reference solution runs in the sandbox, and its output becomes each expected output."""
    if not llm_configured():
        raise HTTPException(status_code=503, detail="AI co-pilot is not configured")
    base_prompt = (
        f"Write one {payload.difficulty} Python interview problem about: {payload.topic}.\n"
        "The candidate's program reads from standard input and writes to standard output.\n"
        "Use exactly this layout and nothing else:\n\n"
        "TITLE: <short title>\n"
        "PROMPT:\n<problem statement with the exact input and output format and one example>\n"
        "SOLUTION:\n"
        + FENCE + "python\n<a correct Python 3 program that reads stdin and prints to stdout>\n" + FENCE + "\n"
        "INPUTS:\n"
        "- <stdin for test 1>\n"
        "- <stdin for test 2>\n"
        "- <stdin for test 3>\n"
        "- <stdin for test 4, an edge case>\n"
        "Each INPUTS line is one test. Write a line break inside a test as \\n, for example 3\\n1 2 3. "
        "Do not use backticks or quotes around the input."
    )

    feedback = ""
    last_error = "AI draft failed"
    for _attempt in range(2):
        try:
            draft = parse_problem_text(complete(base_prompt + feedback, max_tokens=1500))
        except LLMError as exc:
            last_error = str(exc)
            feedback = f"\n\nYour previous reply was rejected: {last_error}. Follow the layout exactly."
            continue
        tests, failure = _run_reference(draft["reference_solution"], draft["test_inputs"])
        if failure is None:
            return {
                "title": draft["title"],
                "prompt": draft["prompt"],
                "difficulty": payload.difficulty,
                "time_limit_s": 900,
                "reference_solution": draft["reference_solution"],
                "tests": tests,
            }
        last_error = f"AI draft failed: {failure}"
        feedback = f"\n\nYour previous solution failed: {failure}. Fix the solution and keep the layout."
    raise HTTPException(status_code=502, detail=last_error)


@router.post("/{problem_id}/tests", response_model=TestCaseOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def add_test_case(problem_id: int, payload: TestCaseCreate, db: Session = Depends(get_db)) -> dict:
    _get_or_404(db, problem_id)
    test = TestCase(problem_id=problem_id, **payload.model_dump())
    db.add(test)
    db.commit()
    db.refresh(test)
    return _public_test(test)


@router.get("/{problem_id}/tests", response_model=list[TestCaseOut])
def list_test_cases(problem_id: int, db: Session = Depends(get_db)) -> list[dict]:
    _get_or_404(db, problem_id)
    tests = db.scalars(select(TestCase).where(TestCase.problem_id == problem_id).order_by(TestCase.id))
    return [_public_test(t) for t in tests]
