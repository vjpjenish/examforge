from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import DocumentKind, JobStatus, QuestionType, ReviewStatus, Role


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth ---------------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORM):
    id: int
    email: str
    name: str
    role: Role


class TokenOut(BaseModel):
    token: str
    user: UserOut


# --- catalog ------------------------------------------------------------------------
class ExamIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""


class ExamOut(ORM):
    id: int
    name: str
    description: str


class InstitutionOut(ORM):
    id: int
    name: str


# --- documents & extraction ----------------------------------------------------------
class JobOut(ORM):
    id: int
    status: JobStatus
    stage: str
    progress: float
    error: str | None
    stats: dict | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class DocumentOut(ORM):
    id: int
    title: str
    kind: DocumentKind
    exam: ExamOut | None
    institution: InstitutionOut | None
    year: int | None
    page_count: int
    profile: dict | None
    created_at: datetime
    solutions_for_id: int | None = None
    duration_minutes: int | None = None
    marks_correct: float | None = None
    marks_incorrect: float | None = None
    latest_job: JobOut | None = None
    question_counts: dict[str, int] = {}
    # Linked solution/answer-key documents, and the test this paper was published as.
    solutions: list[dict] = []
    test_id: int | None = None
    answer_key_entries: int | None = None


# --- questions ----------------------------------------------------------------------
class OptionIO(BaseModel):
    label: str
    text: str = ""
    image: str | None = None


class QuestionOut(ORM):
    id: int
    document_id: int | None
    exam_id: int | None
    order_index: int
    number: str
    section: str
    subject: str | None
    topic: str | None
    difficulty: str | None
    year: int | None
    type: QuestionType
    text: str
    options: list[OptionIO]
    answer: Any
    explanation: str | None
    images: list[dict]
    source_pages: list[int]
    confidence: float
    issues: list[str]
    review_status: ReviewStatus
    answer_source: str | None = None
    edit_count: int = 0


class QuestionPatch(BaseModel):
    number: str | None = None
    section: str | None = None
    subject: str | None = None
    topic: str | None = None
    difficulty: str | None = None
    type: QuestionType | None = None
    text: str | None = None
    options: list[OptionIO] | None = None
    answer: Any = None
    explanation: str | None = None
    review_status: ReviewStatus | None = None


class PublishTestIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    duration_minutes: int = Field(60, ge=1, le=600)
    marks_correct: float = 4.0
    marks_incorrect: float = -1.0
    marks_unattempted: float = 0.0
    include_unreviewed: bool = False
    publish: bool = True


# --- tests & attempts ----------------------------------------------------------------
class TestOut(ORM):
    id: int
    title: str
    description: str
    exam: ExamOut | None
    duration_minutes: int
    marks_correct: float
    marks_incorrect: float
    marks_unattempted: float
    is_published: bool
    created_at: datetime
    question_count: int = 0
    sections: list[str] = []
    my_attempts: int = 0
    in_progress_attempt_id: int | None = None


class TestPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    duration_minutes: int | None = Field(None, ge=1, le=600)
    marks_correct: float | None = None
    marks_incorrect: float | None = None
    marks_unattempted: float | None = None
    is_published: bool | None = None


class SaveAnswerIn(BaseModel):
    response: list[str] | str | None = None
    time_spent_delta: int = Field(0, ge=0, le=3600)
    marked_for_review: bool | None = None
    visited: bool = False


class PyqAnswerIn(BaseModel):
    response: list[str] | str
