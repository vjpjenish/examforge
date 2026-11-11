"""Cancelling an upload must free the extraction queue.

The reported scenario: upload the wrong paper, cancel it, upload the right one -- and the
right one sat in the queue behind the paper that was supposedly cancelled, because
"cancel" only hid the row in the browser and never reached the server.
"""

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
