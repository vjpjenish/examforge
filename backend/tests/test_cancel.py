"""Cancelling an upload must free the extraction queue.

The reported scenario: upload the wrong paper, cancel it, upload the right one -- and the
right one sat in the queue behind the paper that was supposedly cancelled, because
"cancel" only hid the row in the browser and never reached the server.
"""

import pytest

from app.config import get_settings
from app.models import ExtractionJob, JobStatus
from app.worker import claim_next, process

from .conftest import make_pdf


def _upload(client, headers, pdf, title):
    with open(pdf, "rb") as f:
        r = client.post(
            "/api/documents",
            data={"title": title, "kind": "test_series"},
            files={"file": (f"{title}.pdf", f, "application/pdf")},
            headers=headers,
        )
    assert r.status_code == 200, r.text
    return r.json()


def test_cancel_a_queued_job_frees_the_queue(client, admin_headers, tmp_path):
    """The wrong paper is cancelled before a worker claims it, so the next upload runs first."""
    wrong = _upload(client, admin_headers, make_pdf(tmp_path / "wrong.pdf"), "Wrong paper")

    r = client.post(f"/api/documents/{wrong['id']}/cancel", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "canceled"

    right = _upload(client, admin_headers, make_pdf(tmp_path / "right.pdf"), "Right paper")

    # The worker must skip the cancelled job entirely and pick up the newer upload.
    claimed = claim_next()
    assert claimed == right["latest_job"]["id"], "a cancelled job must never be claimed"
    process(claimed)

    assert client.get(f"/api/documents/{right['id']}", headers=admin_headers).json()["latest_job"]["status"] == "completed"
    assert client.get(f"/api/documents/{wrong['id']}", headers=admin_headers).json()["latest_job"]["status"] == "canceled"
    assert claim_next() is None, "nothing else should be left in the queue"


def test_cancel_a_running_job_stops_the_pipeline(client, admin_headers, tmp_path, monkeypatch):
    """A job already being worked on stops at its next progress checkpoint."""
    doc = _upload(client, admin_headers, make_pdf(tmp_path / "running.pdf"), "Running paper")
    job_id = claim_next()
    assert job_id == doc["latest_job"]["id"]

    # Cancel from "another request" the moment the pipeline reports its first progress.
    from app.db import SessionLocal

    import app.extraction.pipeline as pipeline

    real_run = pipeline.run_job

    def cancel_then_run(db, job, provider=None):
        with SessionLocal() as other:
            other.get(ExtractionJob, job.id).status = JobStatus.canceled
            other.commit()
        return real_run(db, job, provider)

    monkeypatch.setattr(pipeline, "run_job", cancel_then_run)
    monkeypatch.setattr("app.worker.run_job", cancel_then_run)
    process(job_id)

    detail = client.get(f"/api/documents/{doc['id']}", headers=admin_headers).json()
    assert detail["latest_job"]["status"] == "canceled", detail["latest_job"]
    assert detail["latest_job"]["error"] is None, "cancelling is not a failure"
    assert claim_next() is None


def test_cancel_requires_an_extraction_in_progress(client, admin_headers, tmp_path):
    doc = _upload(client, admin_headers, make_pdf(tmp_path / "done.pdf"), "Finished paper")
    process(claim_next())
    r = client.post(f"/api/documents/{doc['id']}/cancel", headers=admin_headers)
    assert r.status_code == 409


def test_a_cancelled_document_can_be_re_extracted(client, admin_headers, tmp_path):
    doc = _upload(client, admin_headers, make_pdf(tmp_path / "retry.pdf"), "Retry paper")
    client.post(f"/api/documents/{doc['id']}/cancel", headers=admin_headers)
    r = client.post(f"/api/documents/{doc['id']}/reextract", headers=admin_headers)
    assert r.status_code == 200, r.text
    process(claim_next())
    assert client.get(f"/api/documents/{doc['id']}", headers=admin_headers).json()["latest_job"]["status"] == "completed"


def test_deleting_a_document_removes_its_queued_job(client, admin_headers, tmp_path):
    doc = _upload(client, admin_headers, make_pdf(tmp_path / "gone.pdf"), "Deleted paper")
    assert client.delete(f"/api/documents/{doc['id']}", headers=admin_headers).status_code == 204
    assert claim_next() is None, "deleting a document must take its queued job with it"


def test_a_positive_penalty_never_rewards_wrong_answers(client, admin_headers, tmp_path):
    """Grading adds `marks_incorrect` to the score, so it must be stored negative.

    Found in production: publishing with `marks_incorrect: 0.66` gave 4 correct and 2 wrong a
    score of 5.32 instead of 2.68 -- the wrong answers were *adding* 0.66 each. The upload
    handler and publish.sync_test both normalised the sign; this endpoint did not.
    """
    doc = _upload(client, admin_headers, make_pdf(tmp_path / "penalty.pdf"), "Penalty paper")
    process(claim_next())

    r = client.post(
        f"/api/documents/{doc['id']}/publish-test",
        json={"title": "Fractional penalty", "marks_correct": 1, "marks_incorrect": 0.66},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    test = r.json()
    assert test["marks_incorrect"] == -0.66, "a penalty given as positive must be stored negative"

    # ...and editing the test later must not undo it.
    r = client.patch(f"/api/tests/{test['id']}", json={"marks_incorrect": 0.33}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["marks_incorrect"] == -0.33

    # A wrong answer must reduce the score.
    attempt = client.post(f"/api/tests/{test['id']}/start", headers=admin_headers).json()
    aid = attempt.get("attempt_id") or attempt["id"]
    detail = client.get(f"/api/attempts/{aid}", headers=attempt and admin_headers).json()
    key = {q["id"]: q["answer"] for q in client.get(f"/api/documents/{doc['id']}/questions", headers=admin_headers).json()}
    answered_wrong = 0
    for q in detail["questions"]:
        correct = key.get(q["question_id"])
        if q["type"] != "mcq_single" or not correct:
            continue
        wrong = [o["label"] for o in q["options"] if o["label"] not in correct][:1]
        client.put(f"/api/attempts/{aid}/answers/{q['question_id']}",
                   json={"response": wrong, "visited": True}, headers=admin_headers)
        answered_wrong += 1
    score = client.post(f"/api/attempts/{aid}/submit", headers=admin_headers).json()["score"]
    assert score == pytest.approx(-0.33 * answered_wrong), score
    assert score < 0, "every answer was wrong, so the score must be negative"


def test_no_transaction_is_held_open_across_model_calls(client, admin_headers, tmp_path):
    """The pipeline must not sit inside a transaction while it waits on the model.

    Found in production on Neon: the cancellation check ran a SELECT straight after commit, which
    opened a transaction that then stayed idle for minutes during extraction. Managed Postgres
    terminates idle-in-transaction connections, so the job died at its next write with
    IdleInTransactionSessionTimeout. SQLite has no such timeout, so nothing local caught it.
    """
    from app.db import SessionLocal
    from app.extraction.pipeline import run_job
    from app.extraction.providers import HeuristicProvider
    from app.models import Document

    doc_json = _upload(client, admin_headers, make_pdf(tmp_path / "txn.pdf"), "Transaction paper")

    open_during_call = []

    with SessionLocal() as db:
        job = db.get(ExtractionJob, doc_json["latest_job"]["id"])

        class Probe(HeuristicProvider):
            """Stands in for the model call: records whether a transaction was left open."""

            def extract_chunk(self, *a, **kw):
                open_during_call.append(db.in_transaction())
                return super().extract_chunk(*a, **kw)

            def profile(self, pages):
                open_during_call.append(db.in_transaction())
                return super().profile(pages)

        job.status = JobStatus.running
        db.commit()
        run_job(db, job, Probe(get_settings()))

    assert open_during_call, "the probe never ran, so this asserts nothing"
    assert not any(open_during_call), (
        f"a transaction was open during {sum(open_during_call)} of {len(open_during_call)} model "
        "calls; managed Postgres would terminate the connection"
    )


def test_two_workers_claim_different_jobs(client, admin_headers, tmp_path):
    """With more than one worker, a second upload does not wait behind the first.

    `claim_next` locks the row it takes (FOR UPDATE SKIP LOCKED on Postgres), so two workers must
    never claim the same job, and the second upload must be picked up rather than queued.
    """
    first = _upload(client, admin_headers, make_pdf(tmp_path / "one.pdf"), "First paper")
    second = _upload(client, admin_headers, make_pdf(tmp_path / "two.pdf"), "Second paper")

    a, b = claim_next(), claim_next()
    assert a is not None and b is not None, "both uploads should be claimable at once"
    assert a != b, "two workers must never claim the same job"
    assert {a, b} == {first["latest_job"]["id"], second["latest_job"]["id"]}
    assert claim_next() is None

    process(a)
    process(b)
    for doc in (first, second):
        detail = client.get(f"/api/documents/{doc['id']}", headers=admin_headers).json()
        assert detail["latest_job"]["status"] == "completed"


def test_worker_count_starts_that_many_threads(monkeypatch):
    import threading

    from app import worker as worker_module

    started = []
    monkeypatch.setattr(worker_module, "run_forever", lambda stop, **kw: started.append(threading.current_thread().name))
    stop = worker_module.start_embedded(3)
    for t in threading.enumerate():
        if t.name.startswith("extraction-worker-"):
            t.join(timeout=2)
    stop.set()
    assert len(started) == 3, started
    assert sorted(started) == ["extraction-worker-1", "extraction-worker-2", "extraction-worker-3"]
