"""Previous-year question bank with per-user solved/unsolved tracking."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Document, DocumentKind, Exam, PyqProgress, Question, ReviewStatus, User
from app.schemas import PyqAnswerIn
from app.security import current_user, require_admin
from app.services.grading import is_correct

router = APIRouter(prefix="/api/pyq", tags=["pyq"])


def _bank():
    return (
        select(Question)
        .join(Document, Question.document_id == Document.id)
        .where(Document.kind == DocumentKind.pyq, Question.review_status == ReviewStatus.approved)
    )


def _scoped(stmt, exam_id: int | None, unassigned: bool):
    """Narrow a bank query to one workspace.

    A workspace is an exam. Papers uploaded without one still need somewhere to
    live, so `unassigned` collects those rather than hiding them.
    """
    if unassigned:
        return stmt.where(Question.exam_id.is_(None))
    if exam_id:
        return stmt.where(Question.exam_id == exam_id)
    return stmt


def _public(q: Question, p: PyqProgress | None, reveal: bool) -> dict:
    return {
        "id": q.id,
        "exam_id": q.exam_id,
        "year": q.year,
        "number": q.number,
        "section": q.section,
        "subject": q.subject,
        "topic": q.topic,
        "difficulty": q.difficulty,
        "type": q.type.value,
        "text": q.text,
        "options": q.options,
        "images": q.images,
        "answer": q.answer if reveal else None,
        "explanation": q.explanation if reveal else None,
        "progress": {
            "solved": p.solved,
            "is_correct": p.is_correct,
            "attempts": p.attempts,
            "bookmarked": p.bookmarked,
            "last_response": p.last_response,
        } if p else None,
    }


@router.get("")
def list_pyq(
    exam_id: int | None = None,
    unassigned: bool = False,
    subject: str | None = None,
    year: int | None = None,
    status: str | None = Query(None, pattern="^(solved|unsolved|bookmarked|incorrect)$"),
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = _bank().outerjoin(
        PyqProgress, and_(PyqProgress.question_id == Question.id, PyqProgress.user_id == user.id)
    ).add_columns(PyqProgress)
    stmt = _scoped(stmt, exam_id, unassigned)
    if subject:
        stmt = stmt.where(func.coalesce(Question.subject, Question.section) == subject)
    if year:
        stmt = stmt.where(Question.year == year)
    if q:
        stmt = stmt.where(Question.text.ilike(f"%{q}%"))
    if status == "solved":
        stmt = stmt.where(PyqProgress.solved.is_(True))
    elif status == "unsolved":
        stmt = stmt.where(func.coalesce(PyqProgress.solved, False).is_(False))
    elif status == "bookmarked":
        stmt = stmt.where(PyqProgress.bookmarked.is_(True))
    elif status == "incorrect":
        stmt = stmt.where(PyqProgress.is_correct.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(
        stmt.order_by(Question.year.desc().nulls_last(), Question.document_id, Question.order_index)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_public(question, progress, reveal=bool(progress and progress.solved)) for question, progress in rows],
    }


@router.get("/filters")
def filters(
    exam_id: int | None = None,
    unassigned: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    bank = _scoped(_bank(), exam_id, unassigned).subquery()
    subjects = db.scalars(
        select(func.coalesce(bank.c.subject, bank.c.section)).distinct().order_by(func.coalesce(bank.c.subject, bank.c.section))
    ).all()
    years = db.scalars(select(bank.c.year).where(bank.c.year.is_not(None)).distinct().order_by(bank.c.year.desc())).all()
    return {"subjects": [s for s in subjects if s], "years": years}


@router.get("/stats")
def stats(
    exam_id: int | None = None,
    unassigned: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    bank = _scoped(_bank(), exam_id, unassigned).subquery()
    subject = func.coalesce(bank.c.subject, bank.c.section)
    rows = db.execute(
        select(
            subject,
            func.count(),
            func.count(PyqProgress.id).filter(PyqProgress.solved.is_(True)),
            func.count(PyqProgress.id).filter(PyqProgress.is_correct.is_(True)),
        )
        .select_from(bank)
        .outerjoin(PyqProgress, and_(PyqProgress.question_id == bank.c.id, PyqProgress.user_id == user.id))
        .group_by(subject)
        .order_by(subject)
    ).all()
    by_subject = [{"subject": s or "General", "total": t, "solved": sv, "correct": c} for s, t, sv, c in rows]
    total = sum(r["total"] for r in by_subject)
    solved = sum(r["solved"] for r in by_subject)
    correct = sum(r["correct"] for r in by_subject)
    return {
        "total": total,
        "solved": solved,
        "correct": correct,
        "accuracy": round(100 * correct / solved, 1) if solved else 0.0,
        "by_subject": by_subject,
    }


@router.get("/workspaces")
def workspaces(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """One entry per exam represented in the bank, plus an "Unsorted" bucket.

    Named after the exam chosen when the PYQ paper was uploaded, so a student can
    keep one exam's questions apart from another's.
    """
    bank = _bank().subquery()
    rows = db.execute(
        select(
            bank.c.exam_id,
            func.count(),
            func.count(PyqProgress.id).filter(PyqProgress.solved.is_(True)),
            func.count(PyqProgress.id).filter(PyqProgress.is_correct.is_(True)),
            func.min(bank.c.year),
            func.max(bank.c.year),
            func.count(func.distinct(func.coalesce(bank.c.subject, bank.c.section))),
        )
        .select_from(bank)
        .outerjoin(PyqProgress, and_(PyqProgress.question_id == bank.c.id, PyqProgress.user_id == user.id))
        .group_by(bank.c.exam_id)
    ).all()

    names = {e.id: e.name for e in db.scalars(select(Exam)).all()}
    out = []
    for exam_id, total, solved, correct, year_from, year_to, subjects in rows:
        out.append({
            "exam_id": exam_id,
            "name": names.get(exam_id) or "Unsorted",
            "unassigned": exam_id is None,
            "total": total,
            "solved": solved,
            "correct": correct,
            "accuracy": round(100 * correct / solved, 1) if solved else 0.0,
            "year_from": year_from,
            "year_to": year_to,
            "subjects": subjects,
        })
    # Real exams first, biggest bank first; the unsorted bucket sits at the end.
    out.sort(key=lambda w: (w["unassigned"], -w["total"], w["name"]))
    return out


@router.post("/{question_id}/answer")
def answer(question_id: int, body: PyqAnswerIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    question = db.scalar(_bank().where(Question.id == question_id))
    if question is None:
        raise HTTPException(404, "Question not found")
    p = _progress(db, user, question_id)
    p.attempts = (p.attempts or 0) + 1
    p.solved = True
    p.is_correct = is_correct(question, body.response)
    p.last_response = body.response
    db.commit()
    return _public(question, p, reveal=True)


@router.delete("/{question_id}", status_code=204)
def remove_from_bank(question_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Take one question out of the PYQ bank.

    The row is kept and marked `rejected` rather than deleted: re-extracting the paper re-inserts every
    question it finds, so a hard delete would silently come back (see `services/publish.py`). Rejected is
    the one state publishing never overrides, and it keeps each person's progress for the question in
    case an admin puts it back."""
    question = db.scalar(_bank().where(Question.id == question_id))
    if question is None:
        raise HTTPException(404, "Question not found")
    question.review_status = ReviewStatus.rejected
    db.commit()


@router.post("/{question_id}/bookmark")
def bookmark(question_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if db.scalar(_bank().where(Question.id == question_id)) is None:
        raise HTTPException(404, "Question not found")
    p = _progress(db, user, question_id)
    p.bookmarked = not p.bookmarked
    db.commit()
    return {"bookmarked": p.bookmarked}


def _progress(db: Session, user: User, question_id: int) -> PyqProgress:
    p = db.scalar(select(PyqProgress).where(PyqProgress.user_id == user.id, PyqProgress.question_id == question_id))
    if p is None:
        p = PyqProgress(user_id=user.id, question_id=question_id, solved=False, bookmarked=False, attempts=0)
        db.add(p)
    return p
