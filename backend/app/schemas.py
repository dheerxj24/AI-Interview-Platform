from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Difficulty = Literal["easy", "medium", "hard"]
SessionStatus = Literal["scheduled", "live", "ended"]
RunKind = Literal["visible", "full"]


class ProblemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1)
    difficulty: Difficulty = "medium"
    time_limit_s: int = Field(default=900, ge=60, le=7200)


class ProblemUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    prompt: Optional[str] = Field(default=None, min_length=1)
    difficulty: Optional[Difficulty] = None
    time_limit_s: Optional[int] = Field(default=None, ge=60, le=7200)


class ProblemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    prompt: str
    difficulty: str
    time_limit_s: int
    created_at: datetime


class TestCaseCreate(BaseModel):
    input_text: str
    expected_output: str
    is_hidden: bool = False


class TestCaseOut(BaseModel):
    id: int
    is_hidden: bool
    # Hidden tests return null for their input and expected output.
    input_text: Optional[str]
    expected_output: Optional[str]


class SessionCreate(BaseModel):
    problem_id: int
    candidate_name: str = Field(min_length=1, max_length=120)
    interviewer_name: str = Field(min_length=1, max_length=120)


class SessionUpdate(BaseModel):
    status: Optional[SessionStatus] = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    problem_id: int
    candidate_name: str
    interviewer_name: str
    status: str
    created_at: datetime
    started_at: Optional[datetime]
    ended_at: Optional[datetime]


class SnapshotIn(BaseModel):
    code: str = Field(max_length=50_000)


class RunCreate(BaseModel):
    kind: RunKind = "visible"
    code: Optional[str] = Field(default=None, max_length=50_000)


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    kind: str
    status: str
    passed_count: int
    total_count: int
    runtime_ms: int
    output: str
    error: Optional[str]
    created_at: datetime


class ScorecardIn(BaseModel):
    correctness: int = Field(ge=1, le=5)
    communication: int = Field(ge=1, le=5)
    notes: str = Field(default="", max_length=2000)


class ScorecardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: int
    correctness: int
    communication: int
    notes: str
    created_at: datetime


class CopilotOut(BaseModel):
    suggestions: str


EventKind = Literal["tab_hidden", "window_blur", "paste"]


class EventIn(BaseModel):
    kind: EventKind
    detail: str = Field(default="", max_length=200)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    kind: str
    detail: str
    created_at: datetime


class SessionCreated(SessionOut):
    candidate_token: str
    interviewer_token: str


class ProblemDraftIn(BaseModel):
    topic: str = Field(min_length=3, max_length=200)
    difficulty: Difficulty = "easy"


class DraftTest(BaseModel):
    input_text: str
    expected_output: str
    is_hidden: bool


class ProblemDraftOut(BaseModel):
    title: str
    prompt: str
    difficulty: Difficulty
    time_limit_s: int
    reference_solution: str
    tests: list[DraftTest]

