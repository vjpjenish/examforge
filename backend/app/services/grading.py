"""Answer checking and test result analytics."""

from collections import defaultdict
from datetime import datetime, timezone

from app.models import Attempt, AttemptStatus, Question, QuestionType, Test, TestQuestion


def _is_empty(response) -> bool:
    return response is None or response == "" or response == []


def is_correct(question: Question, response) -> bool | None:
    """True/False, or None when the response is empty or the question has no answer key."""
    if _is_empty(response) or question.answer is None:
        return None
    if question.type == QuestionType.numerical:
        key = question.answer if isinstance(question.answer, dict) else {}
        if "value" not in key:
            return None
        try:
            value = float(str(response).strip())
        except ValueError:
            return False
        return abs(value - float(key["value"])) <= float(key.get("tolerance", 0.01)) + 1e-9
    if question.type in (QuestionType.mcq_single, QuestionType.mcq_multi):
        chosen = {response} if isinstance(response, str) else set(response)
        return chosen == set(question.answer)
    return None  # subjective questions are not auto-graded


def marks_for(test: Test, item: TestQuestion, correct: bool | None, attempted: bool) -> float:
    if not attempted:
        return test.marks_unattempted
    if correct is None:
        return 0.0
    if correct:
        return item.marks_correct if item.marks_correct is not None else test.marks_correct
    return item.marks_incorrect if item.marks_incorrect is not None else test.marks_incorrect


def finalize(attempt: Attempt) -> None:
    """Grade every answer and store the summary. Idempotent."""
    test = attempt.test
    answers = {a.question_id: a for a in attempt.answers}
    score = max_score = 0.0
    for item in test.items:
        max_score += item.marks_correct if item.marks_correct is not None else test.marks_correct
        ans = answers.get(item.question_id)
        if ans is None:
            score += test.marks_unattempted
            continue
        attempted = not _is_empty(ans.response)
        ans.is_correct = is_correct(item.question, ans.response) if attempted else None
        ans.marks_awarded = marks_for(test, item, ans.is_correct, attempted)
        score += ans.marks_awarded
    attempt.score = round(score, 2)
    attempt.max_score = round(max_score, 2)
    attempt.status = AttemptStatus.submitted
    attempt.submitted_at = attempt.submitted_at or datetime.now(timezone.utc)
    attempt.summary = build_report(attempt, include_questions=False)


def build_report(attempt: Attempt, include_questions: bool = True) -> dict:
    test = attempt.test
    answers = {a.question_id: a for a in attempt.answers}
    sections: dict[str, dict] = defaultdict(
        lambda: {"score": 0.0, "max_score": 0.0, "correct": 0, "incorrect": 0, "unattempted": 0,
                 "negative_marks": 0.0, "time_seconds": 0, "total": 0}
    )
    topics: dict[str, dict] = defaultdict(lambda: {"correct": 0, "attempted": 0, "total": 0})
    rows = []
    totals = {"correct": 0, "incorrect": 0, "unattempted": 0, "negative_marks": 0.0, "time_seconds": 0}

    for item in test.items:
        q = item.question
        ans = answers.get(q.id)
        attempted = ans is not None and not _is_empty(ans.response)
        correct = ans.is_correct if ans else None
        marks = ans.marks_awarded if ans else test.marks_unattempted
        spent = ans.time_spent_seconds if ans else 0
        status = "unattempted" if not attempted else "correct" if correct else "incorrect" if correct is False else "ungraded"

        s = sections[item.section]
        s["total"] += 1
        s["max_score"] += item.marks_correct if item.marks_correct is not None else test.marks_correct
        s["score"] += marks
        s["time_seconds"] += spent
        totals["time_seconds"] += spent
        if status in ("correct", "incorrect", "unattempted"):
            s[status] += 1
            totals[status] += 1
        if marks < 0:
            s["negative_marks"] += marks
            totals["negative_marks"] += marks

        topic = q.topic or q.subject or item.section
        topics[topic]["total"] += 1
        if attempted:
            topics[topic]["attempted"] += 1
            topics[topic]["correct"] += 1 if correct else 0

        if include_questions:
            rows.append({
                "question_id": q.id,
                "order": item.order_index + 1,
                "number": q.number,
                "section": item.section,
                "topic": q.topic,
                "type": q.type.value,
                "text": q.text,
                "options": q.options,
                "images": q.images,
                "response": ans.response if ans else None,
                "answer": q.answer,
                "explanation": q.explanation,
                "status": status,
                "marks": marks,
                "time_seconds": spent,
                "visits": ans.visits if ans else 0,
                "marked_for_review": ans.marked_for_review if ans else False,
            })

    attempted_n = totals["correct"] + totals["incorrect"]
    report = {
        "attempt_id": attempt.id,
        "test_id": test.id,
        "test_title": test.title,
        "score": attempt.score,
        "max_score": attempt.max_score,
        "total_questions": len(test.items),
        "attempted": attempted_n,
        **totals,
        "negative_marks": round(totals["negative_marks"], 2),
        "accuracy": round(100 * totals["correct"] / attempted_n, 1) if attempted_n else 0.0,
        "duration_seconds": test.duration_minutes * 60,
        "started_at": attempt.started_at.isoformat(),
        "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
        "sections": [
            {"name": name, **{k: round(v, 2) if isinstance(v, float) else v for k, v in s.items()},
             "accuracy": round(100 * s["correct"] / (s["correct"] + s["incorrect"]), 1)
             if s["correct"] + s["incorrect"] else 0.0}
            for name, s in sections.items()
        ],
        "topics": [
            {"name": name, **t, "accuracy": round(100 * t["correct"] / t["attempted"], 1) if t["attempted"] else 0.0}
            for name, t in sorted(topics.items())
        ],
    }
    if include_questions:
        report["questions"] = rows
    return report
