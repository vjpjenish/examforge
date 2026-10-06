"""Online tests: listing, attempting (server-authoritative timer), submitting and results."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Attempt, AttemptAnswer, AttemptStatus, Role, Test, TestQuestion, User
from app.schemas import SaveAnswerIn, TestOut, TestPatch
from app.security import current_user, require_admin
from app.services.grading import build_report, finalize

router = APIRouter(prefix="/api", tags=["tests"])
GRACE = timedelta(seconds=20)  # network latency allowance for the last autosave


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _test_out(db: Session, test: Test, user: User) -> TestOut:
    out = TestOut.model_validate(test)
    out.question_count = len(test.items)
    out.sections = list(dict.fromkeys(i.section for i in test.items))
    out.my_attempts = db.scalar(
        select(func.count()).where(
            Attempt.test_id == test.id, Attempt.user_id == user.id, Attempt.status == AttemptStatus.submitted
        )
    ) or 0
    out.in_progress_attempt_id = db.scalar(
        select(Attempt.id).where(
            Attempt.test_id == test.id, Attempt.user_id == user.id, Attempt.status == AttemptStatus.in_progress
        )
    )
    return out


def _visible_test(db: Session, test_id: int, user: User) -> Test:
    test = db.get(Test, test_id)
    if test is None or (not test.is_published and user.role != Role.admin):
        raise HTTPException(404, "Test not found")
    return test


@router.get("/tests", response_model=list[TestOut])
def list_tests(exam_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Test).order_by(Test.created_at.desc())
    if user.role != Role.admin:
        stmt = stmt.where(Test.is_published.is_(True))
    if exam_id:
        stmt = stmt.where(Test.exam_id == exam_id)
    return [_test_out(db, t, user) for t in db.scalars(stmt).all()]


@router.get("/tests/{test_id}", response_model=TestOut)
def get_test(test_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _test_out(db, _visible_test(db, test_id, user), user)


@router.patch("/tests/{test_id}", response_model=TestOut)
def update_test(test_id: int, body: TestPatch, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    test = _visible_test(db, test_id, admin)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(test, key, value)
    db.commit()
    return _test_out(db, test, admin)


@router.delete("/tests/{test_id}", status_code=204)
def delete_test(test_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    db.delete(_visible_test(db, test_id, admin))
    db.commit()


@router.post("/tests/{test_id}/start")
def start_attempt(test_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    test = _visible_test(db, test_id, user)
    if not test.items:
        raise HTTPException(400, "This test has no questions")
    existing = db.scalar(
        select(Attempt).where(
            Attempt.test_id == test.id, Attempt.user_id == user.id, Attempt.status == AttemptStatus.in_progress
        )
    )
    if existing and _aware(existing.deadline_at) + GRACE > _now():
        return {"attempt_id": existing.id, "resumed": True}
    if existing:
        finalize(existing)
    now = _now()
    attempt = Attempt(
        test_id=test.id, user_id=user.id, started_at=now, deadline_at=now + timedelta(minutes=test.duration_minutes)
    )
    db.add(attempt)
    db.commit()
    return {"attempt_id": attempt.id, "resumed": False}


def _own_attempt(db: Session, attempt_id: int, user: User) -> Attempt:
    attempt = db.get(Attempt, attempt_id)
    if attempt is None or (attempt.user_id != user.id and user.role != Role.admin):
        raise HTTPException(404, "Attempt not found")
    if attempt.status == AttemptStatus.in_progress and _aware(attempt.deadline_at) + GRACE < _now():
        finalize(attempt)  # time ran out while the student was away
        db.commit()
    return attempt


@router.get("/attempts/{attempt_id}")
def get_attempt(attempt_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    attempt = _own_attempt(db, attempt_id, user)
    test = attempt.test
    answers = {a.question_id: a for a in attempt.answers}
    questions = []
    for item in test.items:
        q, a = item.question, answers.get(item.question_id)
        questions.append({
            "question_id": q.id,
            "order": item.order_index + 1,
            "section": item.section,
            "number": q.number,
            "type": q.type.value,
            "text": q.text,
            "options": [{k: o.get(k) for k in ("label", "text", "image")} for o in q.options],
            "images": q.images,
            "response": a.response if a else None,
            "marked_for_review": a.marked_for_review if a else False,
            "time_spent_seconds": a.time_spent_seconds if a else 0,
            "visited": bool(a and a.visits),
        })
    return {
        "id": attempt.id,
        "status": attempt.status.value,
        "test": {
            "id": test.id,
            "title": test.title,
            "duration_minutes": test.duration_minutes,
            "marks_correct": test.marks_correct,
            "marks_incorrect": test.marks_incorrect,
            "sections": list(dict.fromkeys(i.section for i in test.items)),
        },
        "server_now": _now().isoformat(),
        "deadline_at": _aware(attempt.deadline_at).isoformat(),
        "questions": questions,
    }


@router.put("/attempts/{attempt_id}/answers/{question_id}")
def save_answer(
    attempt_id: int, question_id: int, body: SaveAnswerIn, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    attempt = _own_attempt(db, attempt_id, user)
    if attempt.user_id != user.id:
        raise HTTPException(403, "Not your attempt")
    if attempt.status != AttemptStatus.in_progress:
        raise HTTPException(409, "This attempt has already been submitted")
    in_test = db.scalar(
        select(TestQuestion.id).where(TestQuestion.test_id == attempt.test_id, TestQuestion.question_id == question_id)
    )
    if in_test is None:
        raise HTTPException(404, "Question is not part of this test")
    ans = next((a for a in attempt.answers if a.question_id == question_id), None)
    if ans is None:
        ans = AttemptAnswer(question_id=question_id, response=None, time_spent_seconds=0, visits=0)
        attempt.answers.append(ans)
    if "response" in body.model_fields_set:
        ans.response = body.response
    if body.marked_for_review is not None:
        ans.marked_for_review = body.marked_for_review
    ans.time_spent_seconds = (ans.time_spent_seconds or 0) + body.time_spent_delta
    if body.visited:
        ans.visits = (ans.visits or 0) + 1
    db.commit()
    return {"ok": True}


@router.post("/attempts/{attempt_id}/submit")
def submit_attempt(attempt_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    attempt = _own_attempt(db, attempt_id, user)
    if attempt.status == AttemptStatus.in_progress:
        finalize(attempt)
        db.commit()
    return {"attempt_id": attempt.id, "score": attempt.score, "max_score": attempt.max_score}


@router.get("/attempts/{attempt_id}/report")
def attempt_report(attempt_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    attempt = _own_attempt(db, attempt_id, user)
    if attempt.status != AttemptStatus.submitted:
        raise HTTPException(409, "Submit the test to see the analysis")
    report = build_report(attempt)
    # Rank among all submitted attempts of this test.
    scores = db.scalars(
        select(Attempt.score).where(Attempt.test_id == attempt.test_id, Attempt.status == AttemptStatus.submitted)
    ).all()
    better = sum(1 for s in scores if (s or 0) > (attempt.score or 0))
    report["rank"] = better + 1
    report["total_attempts"] = len(scores)
    report["percentile"] = round(100 * (len(scores) - better - 1) / max(1, len(scores) - 1), 1) if len(scores) > 1 else 100.0
    return report


@router.get("/attempts")
def my_attempts(db: Session = Depends(get_db), user: User = Depends(current_user)):
    attempts = db.scalars(
        select(Attempt).where(Attempt.user_id == user.id).order_by(Attempt.started_at.desc()).limit(100)
    ).all()
    return [
        {
            "id": a.id,
            "test_id": a.test_id,
            "test_title": a.test.title,
            "status": a.status.value,
            "score": a.score,
            "max_score": a.max_score,
            "accuracy": (a.summary or {}).get("accuracy"),
            "started_at": a.started_at.isoformat(),
            "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
        }
        for a in attempts
    ]
