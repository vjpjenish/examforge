from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.pyq import stats as pyq_stats
from app.db import get_db
from app.models import Attempt, AttemptStatus, User
from app.security import current_user

router = APIRouter(prefix="/api", tags=["dashboard"])

# How far back the dashboard practice heatmap reaches (18 weeks).
ACTIVITY_DAYS = 126


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; treat those as UTC so arithmetic is safe."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _streaks(days: set[date]) -> dict:
    """Current and best run of consecutive days on which the user submitted a test."""
    if not days:
        return {"current": 0, "best": 0}
    ordered = sorted(days)
    best = run = 1
    for prev, cur in zip(ordered, ordered[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        best = max(best, run)

    # The current streak only counts if it reaches today or yesterday — a run that
    # ended three days ago is broken, not ongoing.
    today = datetime.now(timezone.utc).date()
    last = ordered[-1]
    if (today - last).days > 1:
        return {"current": 0, "best": best}
    current, cursor = 1, last
    for day in reversed(ordered[:-1]):
        if (cursor - day).days == 1:
            current += 1
            cursor = day
        elif (cursor - day).days > 1:
            break
    return {"current": current, "best": max(best, current)}


def _continue_card(db: Session, user: User) -> dict | None:
    """The test the user walked away from, so the dashboard can offer to resume it."""
    attempt = db.scalars(
        select(Attempt)
        .where(Attempt.user_id == user.id, Attempt.status == AttemptStatus.in_progress)
        .order_by(Attempt.started_at.desc())
    ).first()
    if attempt is None:
        return None

    total = len(attempt.test.items)
    answered = sum(
        1
        for a in attempt.answers
        if a.response not in (None, "", []) 
    )
    deadline = _aware(attempt.deadline_at)
    now = datetime.now(timezone.utc)
    left = int((deadline - now).total_seconds()) if deadline else 0
    return {
        "attempt_id": attempt.id,
        "test_id": attempt.test_id,
        "test_title": attempt.test.title,
        "sections": sorted({i.section for i in attempt.test.items}),
        "question_count": total,
        "answered": answered,
        "seconds_left": max(0, left),
        "expired": left <= 0,
        "started_at": (_aware(attempt.started_at) or now).isoformat(),
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    attempts = db.scalars(
        select(Attempt)
        .where(Attempt.user_id == user.id, Attempt.status == AttemptStatus.submitted)
        .order_by(Attempt.submitted_at)
    ).all()

    trend, sections = [], defaultdict(lambda: {"correct": 0, "incorrect": 0, "unattempted": 0, "time_seconds": 0})
    total_time = correct = incorrect = 0
    best = None
    now = datetime.now(timezone.utc)
    week_ago, month_ago, two_months_ago = now - timedelta(days=7), now - timedelta(days=30), now - timedelta(days=60)
    days: set[date] = set()
    # Per-day totals behind the dashboard's practice heatmap.
    activity: dict[date, dict] = defaultdict(lambda: {"tests": 0, "seconds": 0})
    heatmap_start = (now - timedelta(days=ACTIVITY_DAYS)).date()
    tests_this_week = seconds_this_week = 0
    this_month: list[float] = []
    last_month: list[float] = []

    for a in attempts:
        s = a.summary or {}
        pct = round(100 * (a.score or 0) / a.max_score, 1) if a.max_score else 0.0
        submitted = _aware(a.submitted_at)
        trend.append({
            "attempt_id": a.id,
            "test_title": a.test.title,
            "date": a.submitted_at.isoformat() if a.submitted_at else None,
            "score": a.score,
            "max_score": a.max_score,
            "percent": pct,
            "accuracy": s.get("accuracy", 0.0),
            "sections": [sec["name"] for sec in s.get("sections", [])],
        })
        best = pct if best is None else max(best, pct)
        correct += s.get("correct", 0)
        incorrect += s.get("incorrect", 0)
        seconds = s.get("time_seconds", 0)
        total_time += seconds
        if submitted:
            days.add(submitted.date())
            if submitted.date() >= heatmap_start:
                cell = activity[submitted.date()]
                cell["tests"] += 1
                cell["seconds"] += seconds
            if submitted >= week_ago:
                tests_this_week += 1
                seconds_this_week += seconds
            if submitted >= month_ago:
                this_month.append(pct)
            elif submitted >= two_months_ago:
                last_month.append(pct)
        for sec in s.get("sections", []):
            agg = sections[sec["name"]]
            for k in agg:
                agg[k] += sec.get(k, 0)

    section_rows = [
        {"name": name, **v, "accuracy": round(100 * v["correct"] / (v["correct"] + v["incorrect"]), 1)
         if v["correct"] + v["incorrect"] else 0.0}
        for name, v in sections.items()
    ]
    section_rows.sort(key=lambda r: r["accuracy"])

    # Only a real month-over-month comparison is meaningful; None renders no delta.
    avg_delta = None
    if this_month and last_month:
        avg_delta = round(sum(this_month) / len(this_month) - sum(last_month) / len(last_month), 1)

    return {
        "user": {"name": user.name},
        "totals": {
            "tests_taken": len(attempts),
            "avg_percent": round(sum(t["percent"] for t in trend) / len(trend), 1) if trend else 0.0,
            "best_percent": best or 0.0,
            "accuracy": round(100 * correct / (correct + incorrect), 1) if correct + incorrect else 0.0,
            "hours_practiced": round(total_time / 3600, 1),
            "tests_this_week": tests_this_week,
            "hours_this_week": round(seconds_this_week / 3600, 1),
            "avg_delta_30d": avg_delta,
        },
        "streak": _streaks(days),
        "activity": {
            "start": heatmap_start.isoformat(),
            "days": [
                {"date": d.isoformat(), "tests": v["tests"], "minutes": round(v["seconds"] / 60)}
                for d, v in sorted(activity.items())
            ],
        },
        "continue_test": _continue_card(db, user),
        "trend": trend[-20:],
        "sections": section_rows,
        # Weakest attempted sections below 60% accuracy.
        "weak_areas": [r["name"] for r in section_rows if r["correct"] + r["incorrect"] > 0 and r["accuracy"] < 60][:3],
        "recent": list(reversed(trend[-5:])),
        "pyq": pyq_stats(exam_id=None, db=db, user=user),
    }
