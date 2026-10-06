"""Database schema.

Organised so one deployment can host many exams, institutions and test series:

    Exam ─┬─ Document (uploaded PDF) ── ExtractionJob
          │        └── Question (AI extracted, reviewed by admins)
          └─ Test ── TestQuestion ── Question
                 └── Attempt ── AttemptAnswer
    User ── PyqProgress ── Question
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    student = "student"
    admin = "admin"


class DocumentKind(str, enum.Enum):
    test_series = "test_series"
    pyq = "pyq"
    # Answer key / explanations for another document (`Document.solutions_for_id`).
    solutions = "solutions"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class QuestionType(str, enum.Enum):
    mcq_single = "mcq_single"
    mcq_multi = "mcq_multi"
    numerical = "numerical"
    subjective = "subjective"


class ReviewStatus(str, enum.Enum):
    needs_review = "needs_review"
    approved = "approved"
    rejected = "rejected"


class AttemptStatus(str, enum.Enum):
    in_progress = "in_progress"
    submitted = "submitted"


def _enum(e: type[enum.Enum]) -> Enum:
    return Enum(e, native_enum=False, length=32)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role), default=Role.student)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    kind: Mapped[DocumentKind] = mapped_column(_enum(DocumentKind))
    exam_id: Mapped[int | None] = mapped_column(ForeignKey("exams.id"), index=True)
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"), index=True)
    year: Mapped[int | None] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    # Layout profile the AI inferred (numbering style, answer key location, sections...).
    profile: Mapped[dict | None] = mapped_column(JsonType)
    # For kind=solutions: the question paper these answers belong to.
    solutions_for_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    # For kind=solutions: parsed entries [{"number", "answer", "numerical_answer", "explanation", "pages", "source"}].
    answer_key: Mapped[list | None] = mapped_column(JsonType)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Marking scheme the admin set when uploading a test series. None falls back to the
    # scheme the AI read off the paper (`profile`), then to the Test defaults.
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    marks_correct: Mapped[float | None] = mapped_column(Float)
    marks_incorrect: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    exam: Mapped[Exam | None] = relationship()
    institution: Mapped[Institution | None] = relationship()
    # `passive_deletes` leaves the cascade to the database (`extraction_jobs.document_id` is NOT NULL,
    # so the ORM's default of nulling it out on delete would fail).
    jobs: Mapped[list["ExtractionJob"]] = relationship(
        back_populates="document", order_by="ExtractionJob.id", cascade="all, delete-orphan", passive_deletes=True
    )
    solutions_for: Mapped["Document | None"] = relationship(remote_side="Document.id", foreign_keys=[solutions_for_id])


class ExtractionJob(Base):
    __tablename__ = "extraction_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus), default=JobStatus.queued, index=True)
    stage: Mapped[str] = mapped_column(String(64), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    stats: Mapped[dict | None] = mapped_column(JsonType)
    worker_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[Document] = relationship(back_populates="jobs")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        Index("ix_questions_exam_subject", "exam_id", "subject"),
        Index("ix_questions_document_order", "document_id", "order_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    exam_id: Mapped[int | None] = mapped_column(ForeignKey("exams.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    number: Mapped[str] = mapped_column(String(32), default="")
    section: Mapped[str] = mapped_column(String(120), default="General")
    subject: Mapped[str | None] = mapped_column(String(120))
    topic: Mapped[str | None] = mapped_column(String(160))
    difficulty: Mapped[str | None] = mapped_column(String(16))
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    type: Mapped[QuestionType] = mapped_column(_enum(QuestionType), default=QuestionType.mcq_single)
    text: Mapped[str] = mapped_column(Text)
    # [{"label": "A", "text": "...", "image": "path or null"}]
    options: Mapped[list] = mapped_column(JsonType, default=list)
    # MCQ: ["A"] / ["A", "C"]; numerical: {"value": 4.5, "tolerance": 0.01} ; None if unknown.
    answer: Mapped[dict | list | None] = mapped_column(JsonType)
    explanation: Mapped[str | None] = mapped_column(Text)
    images: Mapped[list] = mapped_column(JsonType, default=list)
    source_pages: Mapped[list] = mapped_column(JsonType, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    issues: Mapped[list] = mapped_column(JsonType, default=list)
    # Where the answer came from: "inline", "answer_key", "solutions:<document id>"; None when unknown.
    answer_source: Mapped[str | None] = mapped_column(String(64))
    # Content edited by a person (student or admin). Re-extraction never overwrites an edited question.
    edited_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    edit_count: Mapped[int] = mapped_column(Integer, default=0)
    review_status: Mapped[ReviewStatus] = mapped_column(
        _enum(ReviewStatus), default=ReviewStatus.needs_review, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    document: Mapped[Document | None] = relationship()


class Test(Base):
    __tablename__ = "tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    exam_id: Mapped[int | None] = mapped_column(ForeignKey("exams.id"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    marks_correct: Mapped[float] = mapped_column(Float, default=4.0)
    marks_incorrect: Mapped[float] = mapped_column(Float, default=-1.0)
    marks_unattempted: Mapped[float] = mapped_column(Float, default=0.0)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    exam: Mapped[Exam | None] = relationship()
    items: Mapped[list["TestQuestion"]] = relationship(
        back_populates="test", order_by="TestQuestion.order_index", cascade="all, delete-orphan"
    )


class TestQuestion(Base):
    __tablename__ = "test_questions"
    __table_args__ = (UniqueConstraint("test_id", "question_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    order_index: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(120), default="General")
    # Per-question marking overrides (e.g. JEE numerical with no negative marking).
    marks_correct: Mapped[float | None] = mapped_column(Float)
    marks_incorrect: Mapped[float | None] = mapped_column(Float)

    test: Mapped[Test] = relationship(back_populates="items")
    question: Mapped[Question] = relationship()


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[AttemptStatus] = mapped_column(_enum(AttemptStatus), default=AttemptStatus.in_progress)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[float | None] = mapped_column(Float)
    max_score: Mapped[float | None] = mapped_column(Float)
    summary: Mapped[dict | None] = mapped_column(JsonType)

    test: Mapped[Test] = relationship()
    answers: Mapped[list["AttemptAnswer"]] = relationship(back_populates="attempt", cascade="all, delete-orphan")


class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"
    __table_args__ = (UniqueConstraint("attempt_id", "question_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    response: Mapped[list | str | None] = mapped_column(JsonType)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0)
    visits: Mapped[int] = mapped_column(Integer, default=0)
    marked_for_review: Mapped[bool] = mapped_column(Boolean, default=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    marks_awarded: Mapped[float] = mapped_column(Float, default=0.0)

    attempt: Mapped[Attempt] = relationship(back_populates="answers")


class ExamTarget(Base):
    """An exam a student is counting down to on their dashboard. Several are allowed."""

    __tablename__ = "exam_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    # Stored as YYYY-MM-DD: the countdown runs to local midnight of that day, so a
    # date the student picked never shifts because of their timezone.
    target_date: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PyqProgress(Base):
    __tablename__ = "pyq_progress"
    __table_args__ = (UniqueConstraint("user_id", "question_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    solved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    bookmarked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_response: Mapped[list | str | None] = mapped_column(JsonType)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
