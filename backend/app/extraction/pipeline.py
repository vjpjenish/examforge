"""End-to-end extraction of one document.

Question papers:
    render pages (reading-ordered text + images) ─▶ profile the format ─▶ extract page windows in parallel
        ─▶ merge + answer keys (model-read, deterministic, linked solution PDFs) ─▶ validate
        ─▶ re-read pages where the numbering shows missing questions ─▶ re-verify doubtful questions
        ─▶ crop figures ─▶ save (upsert, keeps edits) ─▶ publish

Solution / answer-key PDFs:
    render ─▶ deterministic parse of the text layer (verbatim, no quota) ─▶ model reads only the pages the
        text layer cannot be trusted for (scans, broken fonts) or where entries are missing ─▶ apply to
        the linked question paper ─▶ publish

Nothing is dropped silently: windows that fail are retried, pages that could not be processed and
question numbers that were never found are recorded in the job stats and on the neighbouring questions.
Model responses are cached per page window, so a job stopped by the free-tier quota resumes where it
left off instead of paying for the same pages again.
"""

import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.config import Settings, get_settings
from app.extraction import prompts
from app.extraction.keys import parse_answer_text
from app.extraction.labels import normalize_answer
from app.extraction.merge import (
    ChunkResult,
    MergedQuestion,
    apply_answer_key,
    entry_labels,
    figures_of,
    match_key_entries,
    merge_chunks,
    missing_numbers,
    norm_number,
    norm_section,
    normalise,
    revalidate,
    validate_question,
)
from app.extraction.pdf import PageContent, crop_figure, load_pages
from app.extraction.providers import ExtractionProvider, HeuristicProvider, QuotaExhausted, build_provider
from app.extraction.schemas import AnswerKeyEntry, ChunkExtraction, DocumentProfile
from app.models import (
    AttemptAnswer,
    Document,
    DocumentKind,
    ExtractionJob,
    Question,
    QuestionType,
    ReviewStatus,
)

log = logging.getLogger(__name__)
Progress = Callable[[str, float], None]
# Bump when the page text layer changes shape. The cache is keyed on the document hash and the
# request, so a change in how pages are read would otherwise be invisible to it and a re-extraction
# would replay stale results. "2" = ruled tables are kept as Markdown instead of being flattened.
_TEXT_LAYER_VERSION = "2"
_PROMPT_VERSION = hashlib.sha1(
    (prompts.CHUNK_PROMPT + prompts.FOCUS_PROMPT + prompts.SOLUTIONS_PROMPT + prompts.PROFILE_PROMPT
     + _TEXT_LAYER_VERSION).encode()
).hexdigest()[:10]


# --- response cache -------------------------------------------------------------------------
class ChunkCache:
    """Model responses on disk, keyed by document hash + request. Survives failed and repeated jobs."""

    def __init__(self, directory: Path | None):
        self.dir = directory
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)

    def _path(self, *parts) -> Path | None:
        if self.dir is None:
            return None
        key = hashlib.sha1(json.dumps([_PROMPT_VERSION, *parts], default=str).encode()).hexdigest()
        return self.dir / f"{key}.json"

    def get(self, *parts):
        path = self._path(*parts)
        if path is None or not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def put(self, value, *parts) -> None:
        if (path := self._path(*parts)) is not None:
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def cache_for(doc: Document) -> ChunkCache:
    return ChunkCache(storage.root() / "cache" / doc.sha256)


def _windows(pages: list[PageContent], size: int) -> list[tuple[list[PageContent], PageContent | None]]:
    out = []
    for start in range(0, len(pages), size):
        primary = pages[start : start + size]
        lookahead = pages[start + size] if start + size < len(pages) else None
        out.append((primary, lookahead))
    return out


def _page_windows(pages: list[PageContent], wanted: set[int], size: int):
    """Windows of `size` consecutive wanted pages (each with the following page as lookahead)."""
    by_index = {p.index: p for p in pages}
    out, run = [], []
    for i in sorted(wanted):
        if run and (i != run[-1].index + 1 or len(run) == size):
            out.append(run)
            run = []
        run.append(by_index[i])
    if run:
        out.append(run)
    return [(w, by_index.get(w[-1].index + 1)) for w in out]


def _span(primary: list[PageContent]) -> str:
    first, last = primary[0].index + 1, primary[-1].index + 1
    return f"{first}" if first == last else f"{first}-{last}"


# --- question papers ------------------------------------------------------------------------
def extract_document(
    pdf_path: str,
    provider: ExtractionProvider,
    settings: Settings,
    progress: Progress = lambda stage, pct: None,
    cache: ChunkCache | None = None,
    solution_keys: list[tuple[str, list[AnswerKeyEntry]]] | None = None,
) -> tuple[DocumentProfile, list[MergedQuestion], dict]:
    t0 = time.monotonic()
    cache = cache or ChunkCache(None)
    progress("loading", 0.02)
    pages = load_pages(pdf_path)
    stats: dict = {
        "provider": provider.name,
        "pages": len(pages),
        "scanned_pages": sum(p.is_scanned for p in pages),
        "incomplete_text_pages": [p.index + 1 for p in pages if p.text_incomplete and not p.is_scanned],
    }

    # Answer-key grids / solution blocks printed in the paper itself, read exactly from the text layer.
    parsed = parse_answer_text([p.text for p in pages], [p.rows for p in pages], strict=True)
    printed_keys = parsed.as_entries()
    stats["key_entries_from_text"] = len(printed_keys)

    progress("profiling", 0.08)
    profile = _profile(pages, provider, cache, stats)

    # The regex fallback keeps state (current section, answer-key mode) across pages, so it reads
    # the whole document at once. Model providers get small overlapping windows, in parallel.
    size = len(pages) if provider.name == "heuristic" else max(1, settings.pages_per_chunk)
    windows = _windows(pages, size)
    results = _run_windows(windows, provider, profile, settings, cache, stats, progress, (0.1, 0.62))

    def build(chunk_results: list[ChunkResult]) -> tuple[list[MergedQuestion], dict]:
        questions, merge_stats = merge_chunks(chunk_results, profile, extra_keys=printed_keys)
        for source, entries in solution_keys or []:
            merge_stats["answers_from_key"] += apply_answer_key(questions, entries, source=source, authoritative=True)
        revalidate(questions, profile, merge_stats)
        return questions, merge_stats

    progress("merging", 0.64)
    chunk_results = [r for r in results if r is not None]
    questions, merge_stats = build(chunk_results)

    # Numbering gaps: re-read just the pages between the neighbours, asking for the missing numbers.
    gaps = missing_numbers(questions, profile)
    if gaps and provider.name != "heuristic" and settings.max_recover_calls > 0:
        progress("recovering", 0.68)
        recovered = _recover(questions, gaps, pages, provider, profile, settings, cache, stats)
        if recovered:
            chunk_results += recovered
            questions, merge_stats = build(chunk_results)
    stats.update(merge_stats)

    _verify(questions, pages, provider, profile, settings, stats, progress)

    stats["questions"] = len(questions)
    stats["flagged"] = sum(1 for mq in questions if mq.issues)
    stats["with_answers"] = sum(1 for mq in questions if mq.q.answer or mq.q.numerical_answer)
    stats["with_explanations"] = sum(1 for mq in questions if mq.q.explanation)
    stats["gemini_calls"] = getattr(provider, "calls", 0)
    stats["seconds"] = round(time.monotonic() - t0, 1)
    return profile, questions, stats


def _profile(pages, provider, cache: ChunkCache, stats: dict) -> DocumentProfile:
    if (hit := cache.get("profile", provider.name)) is not None:
        return DocumentProfile.model_validate(hit)
    try:
        profile = provider.profile(pages)
        cache.put(profile.model_dump(), "profile", provider.name)
        return profile
    except QuotaExhausted:
        raise
    except Exception as exc:  # a failed profile must not sink the document: fall back to the text layer
        log.exception("Profiling failed; using the text-layer profile")
        stats["profile_error"] = f"{type(exc).__name__}: {exc}"[:300]
        return HeuristicProvider().profile(pages)


def _run_windows(windows, provider, profile, settings, cache, stats, progress, span, focus_of=None):
    """Extract every window (cached), retrying failures once more after the first pass."""
    results: list[ChunkResult | None] = [None] * len(windows)
    errors: dict[int, str] = {}
    lo, hi = span

    def run(i: int) -> ChunkResult:
        primary, lookahead = windows[i]
        sent = [p.index for p in primary] + ([lookahead.index] if lookahead else [])
        focus = focus_of(i) if focus_of else None
        key = ("chunk", provider.name, sent, focus)
        if (hit := cache.get(*key)) is not None:
            out = ChunkExtraction.model_validate(hit)
        else:
            out = provider.extract_chunk(primary, lookahead, profile, None, focus)
            cache.put(out.model_dump(), *key)
        return ChunkResult(pages=sent, primary_count=len(primary), output=out)

    quota_hit = False
    for attempt in (1, 2):
        todo = [i for i in range(len(windows)) if results[i] is None and not quota_hit]
        if not todo:
            break
        workers = max(1, settings.extraction_concurrency) if attempt == 1 else 1
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run, i): i for i in todo}
            for done, fut in enumerate(as_completed(futures), 1):
                i = futures[fut]
                try:
                    results[i] = fut.result()
                    errors.pop(i, None)
                except QuotaExhausted as exc:
                    quota_hit = True
                    errors[i] = str(exc)
                except Exception as exc:  # one bad window must not sink the document
                    log.exception("Window pages %s failed (attempt %s)", _span(windows[i][0]), attempt)
                    errors[i] = f"{type(exc).__name__}: {exc}"[:300]
                progress("extracting", lo + (hi - lo) * done / len(todo))
    failed = [i for i in range(len(windows)) if results[i] is None]
    stats.setdefault("chunk_errors", [])
    stats["chunk_errors"] += [f"pages {_span(windows[i][0])}: {errors.get(i, 'not processed')}" for i in failed]
    stats.setdefault("unprocessed_pages", [])
    stats["unprocessed_pages"] += [p.index + 1 for i in failed for p in windows[i][0]]
    if failed and len(failed) == len(windows):
        if quota_hit:
            raise QuotaExhausted(
                "The Gemini free-tier quota is used up for today. Finished pages are saved; re-extract later to continue."
            )
        raise RuntimeError("Every page window failed: " + "; ".join(errors.get(i, "") for i in failed[:3]))
    return results


def _recover(questions, gaps, pages, provider, profile, settings, cache, stats) -> list[ChunkResult]:
    by_index = {p.index: p for p in pages}
    plans: list[tuple[list[PageContent], PageContent | None, list[str]]] = []
    for sec, numbers in gaps:
        in_section = [mq for mq in questions if mq.key[0] == sec and mq.key[1].isdigit()]
        # Group consecutive missing numbers; each group is looked for between its neighbours.
        groups: list[list[int]] = []
        for n in numbers:
            if groups and n == groups[-1][-1] + 1:
                groups[-1].append(n)
            else:
                groups.append([n])
        for group in groups:
            before = [mq for mq in in_section if int(mq.key[1]) < group[0]]
            after = [mq for mq in in_section if int(mq.key[1]) > group[-1]]
            first = max((mq.start_page for mq in before), default=0)
            last = min((mq.start_page for mq in after), default=len(pages) - 1)
            span = [by_index[i] for i in range(first, max(first, last) + 1) if i in by_index][:3]
            if span:
                lookahead = by_index.get(span[-1].index + 1)
                plans.append((span, lookahead, [str(n) for n in group]))
    plans = plans[: settings.max_recover_calls]
    if not plans:
        return []
    windows = [(primary, lookahead) for primary, lookahead, _ in plans]
    local: dict = {}
    stats["recovery_calls"] = len(plans)
    try:
        results = _run_windows(
            windows, provider, profile, settings, cache, local, lambda s, p: None, (0, 1), focus_of=lambda i: plans[i][2]
        )
    except Exception as exc:  # recovery is a bonus pass: the gaps stay reported, the document still saves
        log.warning("Recovery pass failed: %s", exc)
        stats["recovery_error"] = f"{type(exc).__name__}: {exc}"[:300]
        return []
    found = []
    for (primary, _, wanted), result in zip(plans, results):
        if result is None:
            continue
        got = {norm_number(q.number) for q in result.output.questions}
        found += [n for n in wanted if n in got]
        # Only keep what was asked for: the rest of the window was already extracted.
        result.output.questions = [q for q in result.output.questions if norm_number(q.number) in set(wanted)]
    stats["recovered_numbers"] = found
    return [r for r in results if r is not None]


def _verify(questions, pages, provider, profile, settings, stats, progress) -> None:
    def needs_check(mq: MergedQuestion) -> bool:
        structural = [i for i in mq.issues if not i.startswith(("No answer", "No numerical answer", "Question(s)"))]
        return bool(structural) or mq.q.confidence < settings.review_confidence_threshold

    flagged = [mq for mq in questions if needs_check(mq)][: settings.max_verify_calls]
    stats["verified"] = 0
    if not flagged or provider.name == "heuristic":
        return
    progress("verifying", 0.75)
    by_index = {p.index: p for p in pages}

    def verify(mq: MergedQuestion) -> None:
        ctx = [by_index[i] for i in sorted({mq.start_page, mq.start_page + 1, *mq.pages}) if i in by_index][:3]
        fixed = provider.verify(mq.q, ctx, mq.issues)
        if fixed is None:
            return
        before = mq.q
        normalise(fixed)
        # The verifier only sees the question's own pages; keep data joined from answer keys elsewhere.
        fixed.answer = fixed.answer or before.answer
        fixed.numerical_answer = fixed.numerical_answer or before.numerical_answer
        fixed.explanation = fixed.explanation or before.explanation
        fixed.section = before.section
        fixed.number = before.number
        figures = figures_of(fixed, [p.index for p in ctx])
        mq.q, mq.figures = fixed, figures or mq.figures
        mq.verified = True
        validate_question(mq, profile)

    with ThreadPoolExecutor(max_workers=max(1, settings.extraction_concurrency)) as pool:
        futures = [pool.submit(verify, mq) for mq in flagged]
        for done, fut in enumerate(as_completed(futures), 1):
            try:
                fut.result()
                stats["verified"] += 1
            except QuotaExhausted:
                stats["verify_skipped"] = "quota"
            except Exception:
                log.exception("Verification call failed")
            progress("verifying", 0.75 + 0.15 * done / len(futures))


# --- solution / answer-key PDFs ----------------------------------------------------------------
def extract_solutions_document(
    pdf_path: str,
    provider: ExtractionProvider,
    settings: Settings,
    progress: Progress = lambda stage, pct: None,
    cache: ChunkCache | None = None,
    expected_numbers: list[str] | None = None,
) -> tuple[list[dict], dict]:
    t0 = time.monotonic()
    cache = cache or ChunkCache(None)
    progress("loading", 0.05)
    pages = load_pages(pdf_path)
    incomplete = {p.index for p in pages if p.text_incomplete}
    stats: dict = {"provider": provider.name, "pages": len(pages), "incomplete_text_pages": sorted(i + 1 for i in incomplete)}

    progress("parsing", 0.15)
    parsed = parse_answer_text([p.text for p in pages], [p.rows for p in pages])
    text_entries = {int(e.number): e for e in parsed.as_entries()}
    conflicts = list(parsed.conflicts)

    # An entry whose text crosses a page the text layer cannot be trusted for may hold another
    # question's explanation (the next question's heading is missing from the text). Re-read those.
    trusted: dict[int, AnswerKeyEntry] = {}
    for n, e in text_entries.items():
        lo, hi = parsed.spans.get(n, (e.page_offset, e.page_offset))
        if not any(i in incomplete for i in range(lo, hi + 1)):
            trusted[n] = e
    if expected_numbers:
        expected = sorted({int(norm_number(n)) for n in expected_numbers if norm_number(n).isdigit()})
    else:
        expected = list(range(1, max(text_entries, default=0) + 1))
    wanted = [n for n in expected if n not in trusted or not (trusted[n].explanation or trusted[n].answer)]

    vision: dict[int, AnswerKeyEntry] = {}
    if wanted and provider.name != "heuristic":
        need = set(incomplete)
        starts = sorted((parsed.spans[n][0], n) for n in trusted if n in parsed.spans)
        for n in wanted:
            below = [p for p, m in starts if m < n]
            above = [p for p, m in starts if m > n]
            lo = below[-1] if below else 0
            hi = above[0] if above else len(pages) - 1
            need.update(range(lo, hi + 1))
        windows = _page_windows(pages, need, max(1, settings.pages_per_chunk))
        stats["vision_pages"] = sorted(i + 1 for i in need)
        progress("reading pages", 0.3)
        vision = _solution_windows(windows, provider, settings, cache, stats, progress, [str(n) for n in wanted])

    entries: list[dict] = []
    for n in sorted(set(trusted) | set(vision) | set(text_entries)):
        text_entry, seen = trusted.get(n), vision.get(n)
        if text_entry and seen:
            a, b = normalize_answer(text_entry.answer), normalize_answer(seen.answer)
            if a and b and a != b:
                conflicts.append(f"Q{n}: text layer says {a}, page image says {b}")
        chosen, source = (text_entry, "text") if text_entry else (seen, "vision") if seen else (text_entries[n], "text-unverified")
        if chosen is None:
            continue
        lo, hi = parsed.spans.get(n, (chosen.page_offset, chosen.page_offset))
        entries.append(
            {
                "number": str(n),
                "section": chosen.section,
                "answer": normalize_answer(chosen.answer),
                "numerical_answer": chosen.numerical_answer,
                "explanation": chosen.explanation,
                "pages": [i + 1 for i in range(lo, hi + 1)] if source != "vision" else [chosen.page_offset + 1],
                "source": source,
            }
        )
    found = {int(e["number"]) for e in entries if e["answer"] or e["numerical_answer"] or e["explanation"]}
    stats.update(
        entries=len(entries),
        from_text=sum(1 for e in entries if e["source"] == "text"),
        from_vision=sum(1 for e in entries if e["source"] == "vision"),
        unverified=[e["number"] for e in entries if e["source"] == "text-unverified"],
        missing=[str(n) for n in expected if n not in found],
        conflicts=conflicts,
        gemini_calls=getattr(provider, "calls", 0),
        seconds=round(time.monotonic() - t0, 1),
    )
    return entries, stats


def _solution_windows(windows, provider, settings, cache, stats, progress, wanted) -> dict[int, AnswerKeyEntry]:
    out: dict[int, AnswerKeyEntry] = {}
    errors, unprocessed = [], []

    def run(primary, lookahead) -> list[AnswerKeyEntry]:
        sent = [p.index for p in primary] + ([lookahead.index] if lookahead else [])
        key = ("solutions", provider.name, sent)
        if (hit := cache.get(*key)) is not None:
            entries = [AnswerKeyEntry.model_validate(e) for e in hit]
        else:
            entries = provider.extract_solutions(primary, lookahead, wanted)
            cache.put([e.model_dump() for e in entries], *key)
        for e in entries:
            e.page_offset = sent[min(max(e.page_offset, 0), len(sent) - 1)]
        return entries

    quota_hit = False
    with ThreadPoolExecutor(max_workers=max(1, settings.extraction_concurrency)) as pool:
        futures = {pool.submit(run, primary, lookahead): primary for primary, lookahead in windows}
        for done, fut in enumerate(as_completed(futures), 1):
            primary = futures[fut]
            try:
                for e in fut.result():
                    n = norm_number(e.number)
                    if n.isdigit():
                        # The window where an entry starts has its full text; a later window only its tail.
                        prev = out.get(int(n))
                        if prev is None or len(e.explanation or "") > len(prev.explanation or ""):
                            out[int(n)] = e
            except QuotaExhausted as exc:
                quota_hit = True
                errors.append(f"pages {_span(primary)}: {exc}")
                unprocessed += [p.index + 1 for p in primary]
            except Exception as exc:
                log.exception("Solutions window pages %s failed", _span(primary))
                errors.append(f"pages {_span(primary)}: {type(exc).__name__}: {exc}"[:300])
                unprocessed += [p.index + 1 for p in primary]
            progress("reading pages", 0.3 + 0.55 * done / len(windows))
    stats["chunk_errors"] = errors
    stats["unprocessed_pages"] = sorted(unprocessed)
    if quota_hit:
        stats["quota_exhausted"] = True
    return out


# --- saving -----------------------------------------------------------------------------------
def _answer_json(mq: MergedQuestion):
    q = mq.q
    if q.question_type == "numerical":
        return numerical_answer_json(q.numerical_answer)
    return q.answer or None


def numerical_answer_json(text: str | None):
    if not text:
        return None
    text = text.strip()
    try:
        return {"value": float(text), "tolerance": 0.01}
    except ValueError:
        # Ranges such as "2.5 to 2.7" or "2.5-2.7"
        nums = re.findall(r"-?\d+(?:\.\d+)?", text)
        if len(nums) == 2:
            lo, hi = sorted(map(float, nums))
            return {"value": (lo + hi) / 2, "tolerance": (hi - lo) / 2, "raw": text}
        return {"raw": text}


def _qkey(section: str | None, number: str) -> tuple[str, str]:
    return (norm_section(section), norm_number(number))


def _referenced(db: Session, question_ids: list[int]) -> set[int]:
    if not question_ids:
        return set()
    used = set(db.scalars(select(AttemptAnswer.question_id).where(AttemptAnswer.question_id.in_(question_ids))))
    return used


def save_questions(db: Session, doc: Document, questions: list[MergedQuestion]) -> dict:
    """Upsert by (section, number): question ids stay stable across re-extraction, so tests, attempts and
    PYQ progress keep pointing at the same rows, and a question a person edited is never overwritten."""
    existing = db.scalars(select(Question).where(Question.document_id == doc.id).order_by(Question.order_index)).all()
    pool: dict[tuple[str, str], list[Question]] = {}
    for row in existing:
        pool.setdefault(_qkey(row.section, row.number), []).append(row)
    counts = {"inserted": 0, "updated": 0, "kept_edited": 0, "removed": 0, "kept_missing": 0}
    seen: set[int] = set()

    for order, mq in enumerate(questions):
        q = mq.q
        stem_images, option_images = [], {}
        for i, fig in enumerate(mq.figures):
            rel = f"figures/doc_{doc.id}/q{order:04d}_{i}.png"
            if crop_figure(doc.file_path, fig.page, fig.box_2d, storage.public_dir() / rel):
                if fig.option_label:
                    option_images[fig.option_label] = rel
                else:
                    stem_images.append({"path": rel, "caption": fig.caption})
        values = dict(
            exam_id=doc.exam_id,
            order_index=order,
            number=q.number,
            section=(q.section or "General")[:120],
            subject=q.subject,
            topic=q.topic,
            difficulty=q.difficulty,
            year=q.year or doc.year,
            type=QuestionType(q.question_type),
            text=q.text,
            options=[{"label": o.label, "text": o.text, "image": option_images.get(o.label)} for o in q.options],
            answer=_answer_json(mq),
            answer_source=mq.answer_source or ("inline" if (q.answer or q.numerical_answer) else None),
            explanation=q.explanation,
            images=stem_images,
            source_pages=[p + 1 for p in mq.pages],
            confidence=round(mq.confidence, 3),
            issues=list(mq.issues),
        )
        candidates = pool.get(_qkey(q.section or "General", q.number)) or []
        row = candidates.pop(0) if candidates else None
        if row is None:
            db.add(Question(document_id=doc.id, review_status=ReviewStatus.needs_review, **values))
            counts["inserted"] += 1
            continue
        seen.add(row.id)
        if row.edit_count:
            # A person corrected this question; keep their version and only note what the PDF now says.
            row.order_index = order
            new_answer = values["answer"]
            if new_answer is not None and new_answer != row.answer:
                note = f"Latest extraction reads the answer as {new_answer}; your edited answer was kept"
                row.issues = [i for i in (row.issues or []) if not i.startswith("Latest extraction")] + [note]
            counts["kept_edited"] += 1
            continue
        for key, value in values.items():
            setattr(row, key, value)
        counts["updated"] += 1

    leftovers = [row for row in existing if row.id not in seen]
    used = _referenced(db, [row.id for row in leftovers])
    for row in leftovers:
        if row.edit_count or row.id in used:
            note = "Not found in the latest extraction of this PDF"
            if note not in (row.issues or []):
                row.issues = [*(row.issues or []), note]
            counts["kept_missing"] += 1
        else:
            db.delete(row)
            counts["removed"] += 1
    db.flush()
    return counts


def apply_solutions(db: Session, paper: Document, solutions: Document) -> dict:
    """Join a solutions document's entries to the paper's saved questions (no re-extraction needed)."""
    entries = [AnswerKeyEntry.model_validate(e) for e in solutions.answer_key or []]
    rows = db.scalars(select(Question).where(Question.document_id == paper.id).order_by(Question.order_index)).all()
    source = f"solutions:{solutions.id}"
    result = {"matched": 0, "answers_added": 0, "explanations_added": 0, "disagreements": 0, "skipped_edited": 0}
    by_entry = {e.number: raw for e, raw in zip(entries, solutions.answer_key or [])}
    for row, entry in zip(rows, match_key_entries([_qkey(r.section, r.number) for r in rows], entries)):
        if entry is None:
            continue
        result["matched"] += 1
        if row.edit_count:
            result["skipped_edited"] += 1
            continue
        stub = _row_as_extracted(row)
        labels, numerical = entry_labels(entry, stub)
        issues = [i for i in (row.issues or []) if source not in i and not i.startswith(("No answer", "No numerical answer"))]
        if row.type in (QuestionType.mcq_single, QuestionType.mcq_multi) and labels:
            if row.answer and sorted(row.answer) != labels and row.answer_source != source:
                issues.append(f"Answer {sorted(row.answer)} disagrees with {source} {labels}")
                result["disagreements"] += 1
            elif not row.answer or row.answer_source == source:
                if row.answer != labels:
                    result["answers_added"] += 1
                row.answer, row.answer_source = labels, source
                if len(labels) > 1:
                    row.type = QuestionType.mcq_multi
        elif numerical and row.type in (QuestionType.numerical, QuestionType.subjective) and not row.answer:
            row.answer, row.answer_source = numerical_answer_json(numerical), source
            row.type = QuestionType.numerical
            result["answers_added"] += 1
        if entry.explanation and (not row.explanation or row.answer_source == source or len(entry.explanation) > len(row.explanation)):
            if row.explanation != entry.explanation:
                result["explanations_added"] += 1
            row.explanation = entry.explanation
        raw = by_entry.get(entry.number) or {}
        if raw.get("source") == "text-unverified":
            issues.append(f"Explanation from {source} could not be checked against the page image")
        if not row.answer and row.type in (QuestionType.mcq_single, QuestionType.mcq_multi):
            issues.append("No answer found")
        row.issues = issues
    db.flush()
    return result


def _row_as_extracted(row: Question):
    from app.extraction.schemas import ExtractedQuestion

    return ExtractedQuestion(
        number=row.number,
        text=row.text,
        options=[{"label": o.get("label", ""), "text": o.get("text", "")} for o in row.options or []],
        confidence=row.confidence,
    )


def linked_solutions(db: Session, paper: Document) -> list[Document]:
    return db.scalars(
        select(Document)
        .where(Document.solutions_for_id == paper.id, Document.kind == DocumentKind.solutions)
        .order_by(Document.id)
    ).all()


# --- jobs -----------------------------------------------------------------------------------
def run_job(db: Session, job: ExtractionJob, provider: ExtractionProvider | None = None) -> None:
    from app.services.publish import publish_document

    settings = get_settings()
    doc = job.document

    def progress(stage: str, pct: float) -> None:
        job.stage, job.progress = stage, round(pct, 3)
        db.commit()

    provider = provider or build_provider(settings)
    cache = cache_for(doc)

    if doc.kind == DocumentKind.solutions:
        paper = doc.solutions_for
        expected = None
        if paper is not None:
            expected = [n for n in db.scalars(select(Question.number).where(Question.document_id == paper.id))] or None
        entries, stats = extract_solutions_document(doc.file_path, provider, settings, progress, cache, expected)
        doc.answer_key = entries
        if paper is not None:
            progress("applying", 0.9)
            stats["applied"] = apply_solutions(db, paper, doc)
            publish_document(db, paper)
        job.stats = stats
        db.commit()
        return

    solution_keys = [
        (f"solutions:{s.id}", [AnswerKeyEntry.model_validate(e) for e in s.answer_key])
        for s in linked_solutions(db, doc)
        if s.answer_key
    ]
    profile, questions, stats = extract_document(doc.file_path, provider, settings, progress, cache, solution_keys)
    progress("saving", 0.92)
    doc.profile = profile.model_dump(exclude_none=True)
    if doc.year is None and profile.year:
        doc.year = profile.year
    stats["saved"] = save_questions(db, doc, questions)
    stats["published"] = publish_document(db, doc)
    job.stats = stats
    db.commit()

