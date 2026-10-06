"""The mistake book: every question a student got wrong, across all their tests.

Also hosts the dashboard's exam countdown, which is small enough not to need a
module of its own.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Attempt, AttemptAnswer, AttemptStatus, ExamTarget, Question, Test, TestQuestion, User
from app.security import current_user

router = APIRouter(prefix="/api", tags=["mistakes"])


@router.get("/mistakes")
def mistakes(
    test_id: int | None = None,
    section: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Wrong answers from submitted attempts, newest first.

    `is_correct` is False only for a question that was answered and graded wrong —
    unattempted questions leave it NULL, so they never show up here.
    """
    rows = db.execute(
        select(AttemptAnswer, Attempt, Question, Test, TestQuestion.section)
        .join(Attempt, AttemptAnswer.attempt_id == Attempt.id)
        .join(Question, AttemptAnswer.question_id == Question.id)
        .join(Test, Attempt.test_id == Test.id)
        .outerjoin(
            TestQuestion,
            and_(TestQuestion.test_id == Attempt.test_id, TestQuestion.question_id == Question.id),
        )
        .where(
            Attempt.user_id == user.id,
            Attempt.status == AttemptStatus.submitted,
            AttemptAnswer.is_correct.is_(False),
        )
        .order_by(Attempt.submitted_at.desc(), TestQuestion.order_index)
    ).all()

    items = []
    for answer, attempt, question, test, test_section in rows:
        items.append({
            "id": answer.id,
            "question_id": question.id,
            "attempt_id": attempt.id,
            "test_id": test.id,
            "test_title": test.title,
            "attempted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
            "section": test_section or question.section,
            "subject": question.subject,
            "topic": question.topic,
            "number": question.number,
            "type": question.type.value,
            "text": question.text,
            "options": question.options,
            "images": question.images,
            "response": answer.response,
            "answer": question.answer,
            "explanation": question.explanation,
            "marks_awarded": answer.marks_awarded,
            "time_spent_seconds": answer.time_spent_seconds,
        })

    # Facets come from the unfiltered set, so the dropdowns never lose their options
    # once a filter is applied.
    tests = sorted({(i["test_id"], i["test_title"]) for i in items}, key=lambda t: t[1])
    sections = sorted({i["section"] for i in items if i["section"]})

    if test_id is not None:
        items = [i for i in items if i["test_id"] == test_id]
    if section:
        items = [i for i in items if i["section"] == section]

    return {
        "total": len(items),
        "items": items,
        "tests": [{"id": i, "title": t} for i, t in tests],
        "sections": sections,
    }


# --- exam countdowns --------------------------------------------------------------------

# Enough to track a main exam plus a few backups, without the dashboard becoming a list.
MAX_TARGETS = 6


class ExamTargetIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("name")
    @classmethod
    def _trim(cls, v: str) -> str:
        if not (v := v.strip()):
            raise ValueError("Give the exam a name")
        return v

    @field_validator("target_date")
    @classmethod
    def _real_date(cls, v: str) -> str:
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError("That is not a real date") from None
        return v


def _out(target: ExamTarget) -> dict:
    return {"id": target.id, "name": target.name, "target_date": target.target_date}


def _owned(db: Session, target_id: int, user: User) -> ExamTarget:
    target = db.get(ExamTarget, target_id)
    if target is None or target.user_id != user.id:
        raise HTTPException(404, "Countdown not found")
    return target


@router.get("/exam-targets")
def list_exam_targets(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Soonest first, so the one that matters most reads at the top."""
    targets = db.scalars(
        select(ExamTarget).where(ExamTarget.user_id == user.id).order_by(ExamTarget.target_date, ExamTarget.id)
    ).all()
    return [_out(t) for t in targets]


@router.post("/exam-targets", status_code=201)
def add_exam_target(body: ExamTargetIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    count = db.scalar(select(func.count()).select_from(ExamTarget).where(ExamTarget.user_id == user.id)) or 0
    if count >= MAX_TARGETS:
        raise HTTPException(409, f"You can track up to {MAX_TARGETS} exams at once")
    target = ExamTarget(user_id=user.id, name=body.name, target_date=body.target_date)
    db.add(target)
    db.commit()
    return _out(target)


@router.put("/exam-targets/{target_id}")
def update_exam_target(
    target_id: int, body: ExamTargetIn, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    target = _owned(db, target_id, user)
    target.name = body.name
    target.target_date = body.target_date
    db.commit()
    return _out(target)


@router.delete("/exam-targets/{target_id}", status_code=204)
def delete_exam_target(target_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.delete(_owned(db, target_id, user))
    db.commit()
