"""End-to-end: upload ➜ extract ➜ auto-publish ➜ attempt ➜ analysis ➜ edits ➜ PYQ bank ➜ dashboard."""

from app.worker import claim_next, process


def _student(client, email="student@test.dev"):
    r = client.post("/api/auth/register", json={"email": email, "name": "Stu", "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _upload(client, headers, pdf, kind="test_series", year=None):
    name = f"JEE Main {kind}"
    exam = next((e for e in client.get("/api/exams", headers=headers).json() if e["name"] == name), None)
    exam = exam or client.post("/api/exams", json={"name": name}, headers=headers).json()
    data = {"title": "Mock 1", "kind": kind, "exam_id": str(exam["id"]), "institution": "Acme Classes"}
    if year:
        data["year"] = str(year)
    with open(pdf, "rb") as f:
        r = client.post("/api/documents", data=data, files={"file": ("mock.pdf", f, "application/pdf")}, headers=headers)
    assert r.status_code == 200, r.text
    doc = r.json()
    job_id = claim_next()
    assert job_id == doc["latest_job"]["id"]
    process(job_id)
    return doc


def test_full_flow(client, admin_headers, sample_pdf):
    doc = _upload(client, admin_headers, sample_pdf)
    detail = client.get(f"/api/documents/{doc['id']}", headers=admin_headers).json()
    assert detail["latest_job"]["status"] == "completed", detail["latest_job"]
    assert detail["page_count"] == 3
    page = client.get(f"/api/documents/{doc['id']}/pages/1.png", headers=admin_headers)
    assert page.status_code == 200 and page.content.startswith(b"\x89PNG")

    qs = client.get(f"/api/documents/{doc['id']}/questions", headers=admin_headers).json()
    assert [q["number"] for q in qs] == ["1", "2", "3", "4"]
    assert [q["section"] for q in qs] == ["PHYSICS", "PHYSICS", "CHEMISTRY", "CHEMISTRY"]
    assert qs[0]["answer"] == ["B"] and qs[2]["answer"] == ["C"]
    assert [o["label"] for o in qs[2]["options"]] == ["A", "B", "C", "D"]  # inline options split
    assert qs[3]["type"] == "numerical" and qs[3]["answer"]["value"] == 2.0

    # No approval step: every question is published and the paper is already a live test.
    assert {q["review_status"] for q in qs} == {"approved"}
    assert detail["test_id"] and detail["latest_job"]["stats"]["published"]["test_id"] == detail["test_id"]
    test = client.get(f"/api/tests/{detail['test_id']}", headers=admin_headers).json()
    assert test["is_published"] and test["question_count"] == 4 and test["sections"] == ["PHYSICS", "CHEMISTRY"]

    # An admin edit clears the validator issues and marks the question as edited.
    r = client.patch(f"/api/questions/{qs[1]['id']}", json={"topic": "Electrostatics"}, headers=admin_headers)
    assert r.json()["review_status"] == "approved" and r.json()["edit_count"] == 1

    student = _student(client)
    assert any(t["id"] == test["id"] for t in client.get("/api/tests", headers=student).json())
    attempt_id = client.post(f"/api/tests/{test['id']}/start", headers=student).json()["attempt_id"]
    attempt = client.get(f"/api/attempts/{attempt_id}", headers=student).json()
    assert all("answer" not in q for q in attempt["questions"])  # answers never leak mid-test
    ids = [q["question_id"] for q in attempt["questions"]]

    save = lambda qid, body: client.put(f"/api/attempts/{attempt_id}/answers/{qid}", json=body, headers=student)
    assert save(ids[0], {"response": ["B"], "time_spent_delta": 40, "visited": True}).status_code == 200  # correct
    save(ids[1], {"response": ["A"], "time_spent_delta": 20})  # wrong
    save(ids[2], {"marked_for_review": True, "time_spent_delta": 5})  # unattempted
    save(ids[3], {"response": "2", "time_spent_delta": 60})  # numerical correct

    # Resuming returns the same attempt.
    assert client.post(f"/api/tests/{test['id']}/start", headers=student).json() == {"attempt_id": attempt_id, "resumed": True}
    assert client.post(f"/api/attempts/{attempt_id}/submit", headers=student).json()["score"] == 7.0
    assert save(ids[2], {"response": ["C"]}).status_code == 409

    report = client.get(f"/api/attempts/{attempt_id}/report", headers=student).json()
    assert (report["correct"], report["incorrect"], report["unattempted"]) == (2, 1, 1)
    assert report["negative_marks"] == -1.0 and report["accuracy"] == 66.7
    assert report["time_seconds"] == 125 and report["rank"] == 1
    physics = next(s for s in report["sections"] if s["name"] == "PHYSICS")
    assert physics["score"] == 3.0 and physics["time_seconds"] == 60
    assert report["questions"][1]["status"] == "incorrect"

    dash = client.get("/api/dashboard", headers=student).json()
    assert dash["totals"]["tests_taken"] == 1 and dash["trend"][0]["score"] == 7.0

    # Other students cannot read this attempt.
    other = _student(client, "other@test.dev")
    assert client.get(f"/api/attempts/{attempt_id}", headers=other).status_code == 404

    # Students can correct published questions, but not change their status.
    r = client.patch(f"/api/questions/{ids[2]}", json={"explanation": "Argon is a noble gas."}, headers=other)
    assert r.status_code == 200 and r.json()["explanation"] == "Argon is a noble gas."
    assert client.patch(f"/api/questions/{ids[2]}", json={"review_status": "rejected"}, headers=other).status_code == 403

    # Re-extracting keeps question ids (attempts stay valid) and never overwrites a person's edit.
    client.post(f"/api/documents/{doc['id']}/reextract", headers=admin_headers)
    process(claim_next())
    again = client.get(f"/api/documents/{doc['id']}/questions", headers=admin_headers).json()
    assert [q["id"] for q in again] == [q["id"] for q in qs]
    assert again[2]["explanation"] == "Argon is a noble gas." and again[2]["edit_count"] == 1
    assert client.get(f"/api/attempts/{attempt_id}/report", headers=student).json()["score"] == 7.0


def test_students_cannot_edit_during_their_test(client, admin_headers, sample_pdf):
    doc = _upload(client, admin_headers, sample_pdf)
    test_id = client.get(f"/api/documents/{doc['id']}", headers=admin_headers).json()["test_id"]
    student = _student(client, "sitting@test.dev")
    attempt_id = client.post(f"/api/tests/{test_id}/start", headers=student).json()["attempt_id"]
    qid = client.get(f"/api/attempts/{attempt_id}", headers=student).json()["questions"][0]["question_id"]
    assert client.get(f"/api/questions/{qid}", headers=student).status_code == 409
    assert client.patch(f"/api/questions/{qid}", json={"text": "x"}, headers=student).status_code == 409


def test_pyq_bank(client, admin_headers, sample_pdf):
    _upload(client, admin_headers, sample_pdf, kind="pyq", year=2023)  # published to the bank automatically
    student = _student(client, "pyq@test.dev")

    bank = client.get("/api/pyq?year=2023", headers=student).json()
    assert bank["total"] == 4 and bank["items"][0]["answer"] is None  # hidden until solved
    qid = bank["items"][0]["id"]
    solved = client.post(f"/api/pyq/{qid}/answer", json={"response": ["B"]}, headers=student).json()
    assert solved["progress"]["is_correct"] is True and solved["answer"] == ["B"]
    assert client.post(f"/api/pyq/{bank['items'][1]['id']}/bookmark", headers=student).json() == {"bookmarked": True}

    assert client.get("/api/pyq?status=solved", headers=student).json()["total"] == 1
    assert client.get("/api/pyq?status=unsolved", headers=student).json()["total"] == 3
    assert client.get("/api/pyq?status=bookmarked", headers=student).json()["total"] == 1
    stats = client.get("/api/pyq/stats", headers=student).json()
    assert stats["solved"] == 1 and stats["total"] == 4
    assert "PHYSICS" in client.get("/api/pyq/filters", headers=student).json()["subjects"]


def test_students_cannot_use_admin_endpoints(client):
    student = _student(client, "nosy@test.dev")
    assert client.get("/api/documents", headers=student).status_code == 403
    assert client.get("/api/documents").status_code == 401


def test_delete_test_series_removes_attempts_with_it(client, admin_headers, sample_pdf):
    """Deleting a test takes its questions-in-test and everyone's attempts with it (FK cascade)."""
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models import Attempt, AttemptAnswer, TestQuestion

    doc = _upload(client, admin_headers, sample_pdf)
    test_id = client.get(f"/api/documents/{doc['id']}", headers=admin_headers).json()["test_id"]
    student = _student(client, "deleted-test@test.dev")
    attempt_id = client.post(f"/api/tests/{test_id}/start", headers=student).json()["attempt_id"]
    qid = client.get(f"/api/attempts/{attempt_id}", headers=student).json()["questions"][0]["question_id"]
    client.put(f"/api/attempts/{attempt_id}/answers/{qid}", json={"response": ["B"]}, headers=student)

    # Students cannot delete a test; admins can.
    assert client.delete(f"/api/tests/{test_id}", headers=student).status_code == 403
    assert client.delete(f"/api/tests/{test_id}", headers=admin_headers).status_code == 204

    assert client.get(f"/api/tests/{test_id}", headers=admin_headers).status_code == 404
    assert not any(t["id"] == test_id for t in client.get("/api/tests", headers=student).json())
    assert client.get(f"/api/attempts/{attempt_id}", headers=student).status_code == 404
    assert client.delete(f"/api/tests/{test_id}", headers=admin_headers).status_code == 404

    with SessionLocal() as db:
        count = lambda model, col: db.scalar(select(func.count()).select_from(model).where(col == test_id))
        assert count(TestQuestion, TestQuestion.test_id) == 0
        assert count(Attempt, Attempt.test_id) == 0
        # The answer rows went with the attempt, rather than being left dangling.
        assert db.scalar(
            select(func.count()).select_from(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt_id)
        ) == 0

    # The source document and its questions are untouched: the test can be published again.
    assert client.get(f"/api/documents/{doc['id']}", headers=admin_headers).status_code == 200
    assert len(client.get(f"/api/documents/{doc['id']}/questions", headers=admin_headers).json()) == 4


def test_delete_pyq_question_removes_it_from_the_bank(client, admin_headers, sample_pdf):
    doc = _upload(client, admin_headers, sample_pdf, kind="pyq", year=2019)
    student = _student(client, "deleted-pyq@test.dev")
    bank = client.get("/api/pyq?year=2019", headers=student).json()
    assert bank["total"] == 4
    qid = bank["items"][0]["id"]
    before = client.get("/api/pyq/stats", headers=student).json()["total"]  # the bank holds other papers too

    assert client.delete(f"/api/pyq/{qid}", headers=student).status_code == 403
    assert client.delete(f"/api/pyq/{qid}", headers=admin_headers).status_code == 204

    after = client.get("/api/pyq?year=2019", headers=student).json()
    assert after["total"] == 3 and all(i["id"] != qid for i in after["items"])
    assert client.get("/api/pyq/stats", headers=student).json()["total"] == before - 1
    # Gone from the bank, so it can no longer be answered or removed twice.
    assert client.post(f"/api/pyq/{qid}/answer", json={"response": ["B"]}, headers=student).status_code == 404
    assert client.delete(f"/api/pyq/{qid}", headers=admin_headers).status_code == 404

    # It is rejected, not deleted: re-extracting the paper must not bring it back.
    client.post(f"/api/documents/{doc['id']}/reextract", headers=admin_headers)
    process(claim_next())
    assert client.get("/api/pyq?year=2019", headers=student).json()["total"] == 3
    rows = client.get(f"/api/documents/{doc['id']}/questions", headers=admin_headers).json()
    assert next(q for q in rows if q["id"] == qid)["review_status"] == "rejected"


def test_delete_document_takes_its_jobs_and_questions(client, admin_headers, sample_pdf):
    """Deleting a document removes its jobs, questions and test, and leaves nothing dangling."""
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models import ExtractionJob, Question, Test

    doc = _upload(client, admin_headers, sample_pdf)
    doc_id = doc["id"]
    test_id = client.get(f"/api/documents/{doc_id}", headers=admin_headers).json()["test_id"]

    assert client.delete(f"/api/documents/{doc_id}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/documents/{doc_id}", headers=admin_headers).status_code == 404

    with SessionLocal() as db:
        n = lambda model, col: db.scalar(select(func.count()).select_from(model).where(col == doc_id))
        assert n(ExtractionJob, ExtractionJob.document_id) == 0
        assert n(Question, Question.document_id) == 0
        # tests.document_id is ON DELETE SET NULL, so the test row survives but is detached.
        test = db.get(Test, test_id)
        assert test is not None and test.document_id is None
