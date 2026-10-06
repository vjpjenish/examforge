"""Automatic publishing of extracted questions.

There is no approval step: as soon as a document is extracted, its questions are published to where
they belong, and anyone can correct them afterwards (edits are kept across re-extraction).

    test_series ─▶ one published Test per document (created once, then kept in sync)
    pyq         ─▶ the PYQ bank (the bank lists published questions of PYQ documents)
    solutions   ─▶ applied to the linked paper, which is then re-published

Questions an admin explicitly rejected stay out. Questions with validator issues are published with
their issues visible, so nothing extracted is hidden.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Attempt, Document, DocumentKind, Question, ReviewStatus, Test, TestQuestion


def _questions(db: Session, doc: Document) -> list[Question]:
    return db.scalars(select(Question).where(Question.document_id == doc.id).order_by(Question.order_index)).all()


def publish_document(db: Session, doc: Document) -> dict:
    questions = _questions(db, doc)
    for q in questions:
        if q.review_status != ReviewStatus.rejected:
            q.review_status = ReviewStatus.approved
    live = [q for q in questions if q.review_status == ReviewStatus.approved]
    result: dict = {"questions": len(live)}
    if doc.kind == DocumentKind.test_series and live:
        test = sync_test(db, doc, live)
        result["test_id"] = test.id
    elif doc.kind == DocumentKind.pyq:
        result["pyq_bank"] = True
    db.flush()
    return result


def sync_test(db: Session, doc: Document, questions: list[Question]) -> Test:
    test = db.scalar(select(Test).where(Test.document_id == doc.id).order_by(Test.id))
    profile = doc.profile or {}
    if test is None:
        test = Test(
            title=doc.title,
            description=f"Auto-published from {doc.title}",
            exam_id=doc.exam_id,
            document_id=doc.id,
            created_by=doc.uploaded_by,
            is_published=True,
        )
        duration = doc.duration_minutes or profile.get("duration_minutes")
        if duration:
            test.duration_minutes = int(duration)
        correct = doc.marks_correct if doc.marks_correct is not None else profile.get("marks_correct")
        if correct:
            test.marks_correct = float(correct)
        incorrect = doc.marks_incorrect if doc.marks_incorrect is not None else profile.get("marks_incorrect")
        if incorrect is not None:
            # Papers print the penalty either way ("-0.66" or "0.66 deducted"); store it as negative.
            test.marks_incorrect = -abs(float(incorrect))
        db.add(test)
        db.flush()

    has_attempts = bool(db.scalar(select(func.count()).select_from(Attempt).where(Attempt.test_id == test.id)))
    by_question = {item.question_id: item for item in test.items}
    wanted = {q.id for q in questions}
    for item in list(test.items):
        # Keep questions students already answered in an attempt; drop anything else that left the paper.
        if item.question_id not in wanted and not has_attempts:
            test.items.remove(item)
    for order, q in enumerate(questions):
        item = by_question.get(q.id)
        if item is None:
            test.items.append(TestQuestion(question_id=q.id, order_index=order, section=q.section or "General"))
        else:
            item.order_index, item.section = order, q.section or "General"
    return test
