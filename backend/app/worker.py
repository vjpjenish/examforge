"""Extraction worker.

Jobs are rows in `extraction_jobs`; workers claim them with `SELECT ... FOR UPDATE SKIP LOCKED`,
so any number of worker processes can run side by side against one Postgres with no broker.

    python -m app.worker
"""

import logging
import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.db import SessionLocal
from app.extraction.pipeline import run_job
from app.models import ExtractionJob, JobStatus

log = logging.getLogger("worker")
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
STALE_AFTER = timedelta(hours=1)


def claim_next() -> int | None:
    with SessionLocal() as db:
        job = db.scalars(
            select(ExtractionJob)
            .where(ExtractionJob.status == JobStatus.queued)
            .order_by(ExtractionJob.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if job is None:
            return None
        job.status = JobStatus.running
        job.worker_id = WORKER_ID
        job.started_at = datetime.now(timezone.utc)
        job.stage, job.progress, job.error = "starting", 0.0, None
        db.commit()
        return job.id


def process(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(ExtractionJob, job_id)
        try:
            run_job(db, job)
            job.status, job.stage, job.progress = JobStatus.completed, "done", 1.0
        except Exception as exc:
            log.exception("Job %s failed", job_id)
            db.rollback()
            job = db.get(ExtractionJob, job_id)
            job.status, job.error = JobStatus.failed, f"{type(exc).__name__}: {exc}"[:4000]
        job.finished_at = datetime.now(timezone.utc)
        db.commit()


def requeue_stale() -> None:
    """Put back jobs whose worker died mid-run."""
    cutoff = datetime.now(timezone.utc) - STALE_AFTER
    with SessionLocal() as db:
        db.execute(
            update(ExtractionJob)
            .where(ExtractionJob.status == JobStatus.running, ExtractionJob.started_at < cutoff)
            .values(status=JobStatus.queued, stage="requeued")
        )
        db.commit()


def run_forever(stop: threading.Event | None = None, poll_seconds: float = 2.0) -> None:
    log.info("Worker %s started", WORKER_ID)
    last_sweep = 0.0
    while not (stop and stop.is_set()):
        if time.monotonic() - last_sweep > 300:
            requeue_stale()
            last_sweep = time.monotonic()
        job_id = claim_next()
        if job_id is None:
            time.sleep(poll_seconds)
            continue
        log.info("Processing job %s", job_id)
        process(job_id)


def start_embedded() -> threading.Event:
    """Run a worker thread inside the API process (handy for local development)."""
    stop = threading.Event()
    threading.Thread(target=run_forever, args=(stop,), daemon=True, name="extraction-worker").start()
    return stop


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from app.db import Base, engine

    Base.metadata.create_all(engine)  # in case the worker starts before the API
    run_forever()
