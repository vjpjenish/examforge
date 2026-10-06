"""Upload PDFs, track extraction, correct questions, publish tests.

Extraction publishes automatically (see app/services/publish.py); admins manage documents, and any
signed-in user can correct a published question.
"""

import re
from difflib import SequenceMatcher

import pymupdf
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import storage
from app.config import get_settings
from app.db import get_db
from app.extraction.pdf import page_count
from app.models import (
    Attempt,
    AttemptStatus,
    Document,
    DocumentKind,
    Exam,
    ExtractionJob,
    Institution,
    JobStatus,
    Question,
    ReviewStatus,
    Role,
    Test,
    TestQuestion,
    User,
)
from app.schemas import (
    DocumentOut,
    ExamIn,
    ExamOut,
    InstitutionOut,
    JobOut,
    PublishTestIn,
    QuestionOut,
    QuestionPatch,
    TestOut,
)
from app.security import current_user, require_admin

router = APIRouter(prefix="/api", tags=["admin"])


# --- catalog ----------------------------------------------------------------------------
@router.get("/exams", response_model=list[ExamOut])
def list_exams(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return db.scalars(select(Exam).order_by(Exam.name)).all()


@router.post("/exams", response_model=ExamOut)
def create_exam(body: ExamIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if db.scalar(select(Exam).where(func.lower(Exam.name) == body.name.strip().lower())):
        raise HTTPException(409, "Exam already exists")
    exam = Exam(name=body.name.strip(), description=body.description)
    db.add(exam)
    db.commit()
    return exam


@router.get("/institutions", response_model=list[InstitutionOut])
def list_institutions(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return db.scalars(select(Institution).order_by(Institution.name)).all()


# --- documents ----------------------------------------------------------------------------
def _is_flagged(confidence: float, issues: list | None) -> bool:
    return bool(issues) or confidence < get_settings().review_confidence_threshold


def _doc_out(db: Session, doc: Document) -> DocumentOut:
    out = DocumentOut.model_validate(doc)
    out.latest_job = JobOut.model_validate(doc.jobs[-1]) if doc.jobs else None
    counts = db.execute(
        select(Question.review_status, func.count()).where(Question.document_id == doc.id).group_by(Question.review_status)
    ).all()
    out.question_counts = {status.value: n for status, n in counts}
    confidences = db.execute(select(Question.confidence, Question.issues).where(Question.document_id == doc.id)).all()
    out.question_counts["flagged"] = sum(1 for c, issues in confidences if _is_flagged(c, issues))
    linked = db.scalars(select(Document).where(Document.solutions_for_id == doc.id).order_by(Document.id)).all()
    out.solutions = [
        {"id": s.id, "title": s.title, "status": s.jobs[-1].status.value if s.jobs else None} for s in linked
    ]
    out.test_id = db.scalar(select(Test.id).where(Test.document_id == doc.id).order_by(Test.id))
    if doc.answer_key is not None:
        out.answer_key_entries = len(doc.answer_key)
    return out


_PAIR_NOISE = re.compile(
    r"\b(qp|q|question|questions|paper|sol|sols|solution|solutions|explanations?|explainations?|answers?|keys?|"
    r"ans|exp|eng|english|hin|hindi|with|and|detailed)\b"
)


def _pair_key(title: str) -> str:
    t = re.sub(r"\(\d+\)", " ", title.casefold())  # "(1)" copy suffixes
    t = re.sub(r"[^0-9a-z]+", " ", t)
    return re.sub(r"\s+", " ", _PAIR_NOISE.sub(" ", t)).strip()


def guess_paper(db: Session, title: str) -> Document | None:
    """The question paper a solutions PDF belongs to, from the titles ("X QP" / "X Solutions")."""
    key = _pair_key(title)
    scored = []
    for doc in db.scalars(select(Document).where(Document.kind != DocumentKind.solutions)).all():
        scored.append((SequenceMatcher(None, key, _pair_key(doc.title)).ratio(), doc.id, doc))
    scored.sort(key=lambda t: (-t[0], -t[1]))
    if scored and scored[0][0] >= 0.8 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.05):
        return scored[0][2]
    return None


@router.post("/documents", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    kind: DocumentKind = Form(...),
    exam_id: int | None = Form(None),
    institution: str | None = Form(None),
    year: int | None = Form(None),
    solutions_for: int | None = Form(None, description="For kind=solutions: id of the question paper"),
    duration_minutes: int | None = Form(None, description="Test series only: minutes allowed"),
    marks_correct: float | None = Form(None, description="Test series only: marks per correct answer"),
    marks_incorrect: float | None = Form(None, description="Test series only: penalty, stored negative"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    data = await file.read()
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"PDF is larger than {get_settings().max_upload_mb} MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "File is not a PDF")
    if exam_id is not None and db.get(Exam, exam_id) is None:
        raise HTTPException(404, "Exam not found")
    if kind is DocumentKind.test_series:
        if duration_minutes is not None and not 1 <= duration_minutes <= 1440:
            raise HTTPException(422, "Duration must be between 1 and 1440 minutes")
        if marks_correct is not None and not 0 < marks_correct <= 100:
            raise HTTPException(422, "Marks per question must be between 0 and 100")
        if marks_incorrect is not None and abs(marks_incorrect) > 100:
            raise HTTPException(422, "Negative marks must be between 0 and 100")
    else:
        # A marking scheme only means something for a test series.
        duration_minutes = marks_correct = marks_incorrect = None
    paper = None
    if kind == DocumentKind.solutions:
        paper = db.get(Document, solutions_for) if solutions_for else guess_paper(db, title or file.filename or "")
        if paper is None or paper.kind == DocumentKind.solutions:
            raise HTTPException(400, "Choose the question paper these solutions belong to")
        exam_id = exam_id or paper.exam_id
        year = year or paper.year
    path, digest = storage.save_pdf(data)
    try:
        pages = page_count(path)
    except Exception:
        raise HTTPException(400, "Could not open this PDF (corrupt or password protected?)")

    inst = None
    if institution and institution.strip():
        inst = db.scalar(select(Institution).where(func.lower(Institution.name) == institution.strip().lower()))
        if inst is None:
            inst = Institution(name=institution.strip())
            db.add(inst)
    doc = Document(
        title=title.strip() or file.filename or "Untitled",
        kind=kind,
        exam_id=exam_id,
        institution=inst,
        year=year,
        file_path=path,
        sha256=digest,
        page_count=pages,
        uploaded_by=admin.id,
        solutions_for_id=paper.id if paper else None,
        duration_minutes=duration_minutes,
        marks_correct=marks_correct,
        # Papers phrase the penalty either way; store it negative so grading can just add it.
        marks_incorrect=None if marks_incorrect is None else -abs(marks_incorrect),
    )
    db.add(doc)
    db.flush()
    db.add(ExtractionJob(document_id=doc.id))
    db.commit()
    db.refresh(doc)
    return _doc_out(db, doc)


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    docs = db.scalars(select(Document).order_by(Document.created_at.desc())).all()
    return [_doc_out(db, d) for d in docs]


def _get_doc(db: Session, doc_id: int) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    return doc


@router.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _doc_out(db, _get_doc(db, doc_id))


@router.post("/documents/{doc_id}/reextract", response_model=JobOut)
def reextract(doc_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    doc = _get_doc(db, doc_id)
    if doc.jobs and doc.jobs[-1].status in (JobStatus.queued, JobStatus.running):
        raise HTTPException(409, "An extraction is already in progress")
    job = ExtractionJob(document_id=doc.id)
    db.add(job)
    db.commit()
    return job


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    db.delete(_get_doc(db, doc_id))
    db.commit()


@router.get("/documents/{doc_id}/pages/{page}.png")
def page_image(doc_id: int, page: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Render one source page so reviewers can compare extracted questions with the original."""
    doc = _get_doc(db, doc_id)
    if not 1 <= page <= doc.page_count:
        raise HTTPException(404, "Page out of range")
    with pymupdf.open(doc.file_path) as pdf:
        png = pdf[page - 1].get_pixmap(dpi=110).tobytes("png")
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    job = db.get(ExtractionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


# --- review ------------------------------------------------------------------------------
@router.get("/documents/{doc_id}/questions", response_model=list[QuestionOut])
def document_questions(
    doc_id: int,
    status: ReviewStatus | None = None,
    flagged: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    stmt = select(Question).where(Question.document_id == doc_id)
    if status:
        stmt = stmt.where(Question.review_status == status)
    questions = db.scalars(stmt.order_by(Question.order_index)).all()
    return [q for q in questions if _is_flagged(q.confidence, q.issues)] if flagged else questions


def _editable_question(db: Session, qid: int, user: User) -> Question:
    q = db.get(Question, qid)
    if q is None:
        raise HTTPException(404, "Question not found")
    if user.role == Role.admin:
        return q
    if q.review_status != ReviewStatus.approved:
        raise HTTPException(404, "Question not found")
    # Editing shows the answer, so not while the student is sitting a test that contains this question.
    live = db.scalar(
        select(func.count())
        .select_from(Attempt)
        .join(TestQuestion, TestQuestion.test_id == Attempt.test_id)
        .where(
            Attempt.user_id == user.id,
            Attempt.status == AttemptStatus.in_progress,
            TestQuestion.question_id == q.id,
        )
    )
    if live:
        raise HTTPException(409, "Finish your test before editing its questions")
    return q


@router.get("/questions/{qid}", response_model=QuestionOut)
def get_question(qid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _editable_question(db, qid, user)


@router.patch("/questions/{qid}", response_model=QuestionOut)
def update_question(qid: int, body: QuestionPatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Correct a published question. Any signed-in user may fix content; only admins change its status."""
    q = _editable_question(db, qid, user)
    data = body.model_dump(exclude_unset=True)
    if "review_status" in data and user.role != Role.admin:
        raise HTTPException(403, "Only admins can change a question's status")
    for key, value in data.items():
        setattr(q, key, value)
    if data.keys() - {"review_status"}:
        # A person edited the content: it is now authoritative and survives re-extraction.
        q.issues, q.confidence = [], 1.0
        q.edited_by, q.edit_count = user.id, (q.edit_count or 0) + 1
        if "answer" in data:
            q.answer_source = "edited"
        if q.review_status != ReviewStatus.rejected:
            q.review_status = data.get("review_status", ReviewStatus.approved)
    db.commit()
    return q


@router.post("/documents/{doc_id}/questions/approve")
def bulk_approve(
    doc_id: int,
    only_clean: bool = Query(True, description="Only approve questions with no validator issues"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    qs = db.scalars(
        select(Question).where(Question.document_id == doc_id, Question.review_status == ReviewStatus.needs_review)
    ).all()
    approved = 0
    for q in qs:
        if only_clean and _is_flagged(q.confidence, q.issues):
            continue
        q.review_status = ReviewStatus.approved
        approved += 1
    db.commit()
    return {"approved": approved}


@router.post("/documents/{doc_id}/publish-test", response_model=TestOut)
def publish_test(doc_id: int, body: PublishTestIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    doc = _get_doc(db, doc_id)
    allowed = [ReviewStatus.approved] + ([ReviewStatus.needs_review] if body.include_unreviewed else [])
    questions = db.scalars(
        select(Question)
        .where(Question.document_id == doc.id, Question.review_status.in_(allowed))
        .order_by(Question.order_index)
    ).all()
    if not questions:
        raise HTTPException(400, "No approved questions to publish. Review and approve questions first.")
    test = Test(
        title=body.title,
        description=body.description,
        exam_id=doc.exam_id,
        document_id=doc.id,
        duration_minutes=body.duration_minutes,
        marks_correct=body.marks_correct,
        marks_incorrect=body.marks_incorrect,
        marks_unattempted=body.marks_unattempted,
        is_published=body.publish,
        created_by=admin.id,
    )
    test.items = [
        TestQuestion(question_id=q.id, order_index=i, section=q.section or "General")
        for i, q in enumerate(questions)
    ]
    db.add(test)
    db.commit()
    out = TestOut.model_validate(test)
    out.question_count = len(questions)
    out.sections = list(dict.fromkeys(i.section for i in test.items))
    return out
