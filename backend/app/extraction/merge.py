"""Turn per-chunk model output into one clean, validated, ordered question list.

Accuracy here comes from cross-checking, not trusting a single model call:
- questions that straddle chunk boundaries are stitched (lookahead + continuation fragments);
- duplicates from overlapping windows are merged, keeping the most complete version; two *different*
  texts under one number are reported as a conflict instead of one silently replacing the other;
- numbered statements that a model split off as "questions" are recognised (their text is already
  inside another question) and folded back;
- answer keys printed elsewhere (same PDF or a separate solutions PDF) are joined back to their questions;
- a validator flags anything structurally suspicious so it can be re-verified and is visible to users.
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.extraction.labels import clean_label, normalize_answer
from app.extraction.schemas import AnswerKeyEntry, ChunkExtraction, DocumentProfile, ExtractedQuestion

_FIGURE_WORDS = re.compile(r"\b(figure|fig\.|diagram|graph|shown (?:below|above|here)|circuit|given image)\b", re.I)
_INSTRUCTION_WORDS = re.compile(
    r"\b(OMR|answer sheet|test booklet|roll number|invigilator|candidates? (?:must|should)|do not open|"
    r"rough work|time allowed|maximum marks)\b",
    re.I,
)
# A second question start inside a stem: a new number followed (later) by its own (a) option.
_EMBEDDED_QUESTION = re.compile(r"\n\s*(?:Q\.?\s*)?(\d{1,3})[.)]\s+\S.*\n(?:.*\n){0,12}?\s*\(?[aA][).]\s", re.M)


@dataclass
class ChunkResult:
    pages: list[int]  # absolute page indices of the images sent: primary pages then lookahead
    primary_count: int
    output: ChunkExtraction


@dataclass
class AbsFigure:
    page: int
    box_2d: list[int]
    caption: str | None = None
    option_label: str | None = None


@dataclass
class MergedQuestion:
    q: ExtractedQuestion
    start_page: int
    figures: list[AbsFigure] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    verified: bool = False
    extra_pages: set[int] = field(default_factory=set)  # pages a continuation came from
    answer_source: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (norm_section(self.q.section), norm_number(self.q.number))

    @property
    def pages(self) -> list[int]:
        return sorted({self.start_page, *self.extra_pages, *(f.page for f in self.figures)})

    @property
    def confidence(self) -> float:
        serious = [i for i in self.issues if not i.startswith("No answer")]
        return max(0.0, min(1.0, self.q.confidence) - 0.15 * len(serious))


def norm_section(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "general")).strip().casefold()


def norm_number(n: str) -> str:
    m = re.search(r"\d+", n or "")
    return str(int(m.group())) if m else (n or "").strip().casefold()


def _plain(text: str) -> str:
    """Comparable form of a text: lower-case letters and digits only."""
    return re.sub(r"[^0-9a-zऀ-ॿ]+", "", (text or "").casefold())


def similar(a: str, b: str) -> float:
    a, b = _plain(a)[:400], _plain(b)[:400]
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def _abs(pages: list[int], offset: int) -> int:
    return pages[min(max(offset, 0), len(pages) - 1)]


def _completeness(q: ExtractedQuestion) -> tuple:
    return (len(q.options), bool(q.answer or q.numerical_answer), len(q.text), q.confidence)


def _absorb(into: MergedQuestion, other: MergedQuestion) -> None:
    """Merge two extractions of the same question, keeping the more complete one as the base."""
    if _completeness(other.q) > _completeness(into.q):
        into.q, other.q = other.q, into.q
        into.start_page, other.start_page = other.start_page, into.start_page
        into.figures, other.figures = other.figures, into.figures
    labels = {o.label for o in into.q.options}
    into.q.options += [o for o in other.q.options if o.label not in labels]
    into.q.answer = into.q.answer or other.q.answer
    into.q.numerical_answer = into.q.numerical_answer or other.q.numerical_answer
    into.q.explanation = into.q.explanation or other.q.explanation
    into.q.year = into.q.year or other.q.year
    seen = {(f.page, tuple(f.box_2d)) for f in into.figures}
    into.figures += [f for f in other.figures if (f.page, tuple(f.box_2d)) not in seen]
    into.extra_pages |= other.extra_pages | {other.start_page}


def figures_of(q: ExtractedQuestion, pages: list[int]) -> list[AbsFigure]:
    figs = [AbsFigure(_abs(pages, b.page_offset), b.box_2d, b.caption) for b in q.figures]
    for o in q.options:
        if o.figure:
            figs.append(AbsFigure(_abs(pages, o.figure.page_offset), o.figure.box_2d, o.figure.caption, o.label))
    return figs


def normalise(q: ExtractedQuestion) -> None:
    q.number = q.number.strip().lstrip("Qq.").strip() or q.number
    seen: set[str] = set()
    opts = []
    for o in q.options:
        o.label = (clean_label(o.label) or "?")[:3]
        if o.label not in seen:
            seen.add(o.label)
            opts.append(o)
    # Options printed as (1)..(4) or (i)..(iv) are stored as A..D, so answers can be matched uniformly.
    labels = [o.label for o in opts]
    if labels and all(label.isdigit() for label in labels) and labels == [str(i + 1) for i in range(len(labels))]:
        for i, o in enumerate(opts):
            o.label = chr(ord("A") + i)
    q.options = opts
    q.answer = normalize_answer(q.answer, [o.label for o in q.options])
    if not q.options and q.question_type in ("mcq_single", "mcq_multi"):
        q.question_type = "numerical" if q.numerical_answer else "subjective"
    if q.question_type == "mcq_single" and len(q.answer) > 1:
        q.question_type = "mcq_multi"


def _contained_in(fragment: str, other: str) -> bool:
    f, o = _plain(fragment), _plain(other)
    return len(f) >= 8 and f in o


def merge_chunks(
    chunks: list[ChunkResult],
    profile: DocumentProfile,
    extra_keys: list[AnswerKeyEntry] | None = None,
) -> tuple[list[MergedQuestion], dict]:
    """Merge chunk outputs. `extra_keys` are answer entries found outside the model output (the
    deterministic key parser); they are authoritative over keys the model read from the same pages."""
    merged: list[MergedQuestion] = []
    by_key: dict[tuple[str, str], MergedQuestion] = {}
    answer_key: list[AnswerKeyEntry] = []
    section: str | None = None
    stats = {
        "raw_questions": 0,
        "duplicates_merged": 0,
        "continuations_stitched": 0,
        "statement_fragments_folded": 0,
        "conflicts": [],
    }

    for chunk in chunks:
        answer_key += chunk.output.answer_key
        for original in chunk.output.questions:
            q = original.model_copy(deep=True)  # merging mutates; chunk results may be merged again later
            stats["raw_questions"] += 1
            normalise(q)
            if q.section:
                section = q.section
            else:
                q.section = section or "General"
            mq = MergedQuestion(q=q, start_page=_abs(chunk.pages, q.page_offset), figures=figures_of(q, chunk.pages))

            if q.continues_from_previous_page:
                target = by_key.get(mq.key) or (merged[-1] if merged else None)
                if target is not None:
                    if q.text and not _contained_in(q.text, target.q.text) and not target.q.options:
                        target.q.text = f"{target.q.text}\n{q.text}".strip()
                    _absorb_tail(target, mq)
                    stats["continuations_stitched"] += 1
                    continue
            if (existing := by_key.get(mq.key)) is not None:
                if similar(existing.q.text, q.text) >= 0.6 or not q.text.strip() or not existing.q.text.strip():
                    _absorb(existing, mq)
                    stats["duplicates_merged"] += 1
                    continue
                # Same number, different text: usually a numbered statement inside another question
                # ("2. Sweden") that collides with the real question 2.
                real, other = (existing, mq) if _completeness(existing.q) >= _completeness(q) else (mq, existing)
                if any(_contained_in(other.q.text, m.q.text) for m in merged if m is not other) or (
                    not other.q.options and len(other.q.text) < 160 and real.q.options
                ):
                    if real is mq:
                        merged[merged.index(existing)] = mq
                        by_key[mq.key] = mq
                    stats["statement_fragments_folded"] += 1
                    continue
                note = f"Conflicting extraction for Q{q.number} (page {other.start_page + 1}): {other.q.text[:160]!r}"
                real.issues.append(note)
                stats["conflicts"].append(note)
                if real is mq:
                    merged[merged.index(existing)] = mq
                    by_key[mq.key] = mq
                continue
            by_key[mq.key] = mq
            merged.append(mq)

    _order(merged)
    stats["statement_fragments_folded"] += _fold_statement_fragments(merged, profile)
    stats["answer_key_entries"] = len(answer_key) + len(extra_keys or [])
    # Model-read keys first, then the deterministic parse, which overrides them where both exist.
    stats["answers_from_key"] = apply_answer_key(merged, answer_key, source="answer_key")
    if extra_keys:
        stats["answers_from_key"] += apply_answer_key(merged, extra_keys, source="answer_key", authoritative=True)
    revalidate(merged, profile, stats)
    return merged, stats


def _order(merged: list[MergedQuestion]) -> None:
    """Paper order: sections in order of first appearance, questions by number within a section.

    Windows finish in any order and recovered questions arrive last, so arrival order is not paper
    order. Un-numbered items stay right after the numbered question they followed."""
    section_rank: dict[str, int] = {}
    keys = []
    last = 0.0
    for i, mq in enumerate(merged):
        rank = section_rank.setdefault(mq.key[0], len(section_rank))
        if mq.key[1].isdigit():
            last = float(mq.key[1])
            keys.append((rank, last, i))
        else:
            keys.append((rank, last + 0.5, i))
    order = sorted(range(len(merged)), key=lambda i: keys[i])
    merged[:] = [merged[i] for i in order]


def _fold_statement_fragments(merged: list[MergedQuestion], profile: DocumentProfile) -> int:
    """Drop 'questions' that are really a numbered statement of the previous question.

    In an MCQ paper a real question has options. An option-less item whose text already appears in the
    question before it (or whose number goes backwards) is a statement the model split off."""
    mcq_share = sum(1 for m in merged if m.q.options) / max(1, len(merged))
    if mcq_share < 0.6:
        return 0
    folded = 0
    out: list[MergedQuestion] = []
    for mq in merged:
        prev = out[-1] if out else None
        if prev is not None and not mq.q.options and prev.q.options:
            goes_back = mq.key[1].isdigit() and prev.key[1].isdigit() and int(mq.key[1]) <= int(prev.key[1])
            if _contained_in(mq.q.text, prev.q.text) or (goes_back and mq.key[0] == prev.key[0]):
                if not _contained_in(mq.q.text, prev.q.text):
                    prev.issues.append(f"A numbered line '{mq.q.number}. {mq.q.text[:80]}' was split off; check the stem")
                folded += 1
                continue
        out.append(mq)
    merged[:] = out
    return folded


def _absorb_tail(target: MergedQuestion, tail: MergedQuestion) -> None:
    """A continuation fragment without a matching number: only take what the target lacks."""
    labels = {o.label for o in target.q.options}
    target.q.options += [o for o in tail.q.options if o.label not in labels]
    target.q.answer = target.q.answer or tail.q.answer
    target.q.numerical_answer = target.q.numerical_answer or tail.q.numerical_answer
    target.q.explanation = target.q.explanation or tail.q.explanation
    target.figures += tail.figures
    target.extra_pages.add(tail.start_page)


def match_key_entries(keys: list[tuple[str, str]], entries: list[AnswerKeyEntry]) -> list[AnswerKeyEntry | None]:
    """Pair questions (section, number) with answer-key entries.

    Entries with a section match on (section, number). Otherwise by number; when numbering restarts per
    section, an un-sectioned key lists the same number once per section, in order, so the n-th question
    numbered 5 takes the n-th entry numbered 5."""
    by_section = {(norm_section(e.section), norm_number(e.number)): e for e in entries if e.section}
    by_number: dict[str, list[AnswerKeyEntry]] = {}
    for e in entries:
        by_number.setdefault(norm_number(e.number), []).append(e)
    number_counts: dict[str, int] = {}
    for _, num in keys:
        number_counts[num] = number_counts.get(num, 0) + 1
    consumed: dict[str, int] = {}
    out: list[AnswerKeyEntry | None] = []
    for sec, num in keys:
        entry = by_section.get((sec, num))
        if entry is None and num in by_number:
            candidates = by_number[num]
            idx = consumed.get(num, 0)
            if number_counts[num] == 1:
                entry = candidates[0]  # duplicates in the key itself: first one wins, consistently
            elif idx < len(candidates) and len(candidates) == number_counts[num]:
                entry = candidates[idx]
            consumed[num] = idx + 1
        out.append(entry)
    return out


def entry_labels(entry: AnswerKeyEntry, q: ExtractedQuestion) -> tuple[list[str], str | None]:
    """An entry's answer in the question's terms: option labels, or a numerical answer."""
    option_labels = [o.label for o in q.options]
    labels = normalize_answer(entry.answer, option_labels)
    numerical = entry.numerical_answer
    # A key that says "3" for a 4-option MCQ means the third option.
    if not labels and numerical and q.options and re.fullmatch(r"\d", numerical.strip()):
        labels = normalize_answer([numerical.strip()], option_labels)
        numerical = None
    return labels, numerical


def apply_answer_key(
    questions: list[MergedQuestion],
    key: list[AnswerKeyEntry],
    source: str,
    authoritative: bool = False,
) -> int:
    """Join key entries to questions. Never overwrites a different existing answer silently: a
    disagreement is recorded as an issue (and an authoritative source replaces a model-read key)."""
    if not key:
        return 0
    applied = 0
    for mq, entry in zip(questions, match_key_entries([m.key for m in questions], key)):
        if entry is None:
            continue
        labels, numerical = entry_labels(entry, mq.q)
        if labels and mq.q.answer and labels != mq.q.answer:
            replace = authoritative and mq.answer_source == "answer_key"
            if not replace:
                mq.issues.append(f"Answer {mq.q.answer} disagrees with {source} {labels}")
            else:
                mq.q.answer, mq.answer_source = labels, source
        if labels and not mq.q.answer:
            mq.q.answer, mq.answer_source = labels, source
            applied += 1
        if numerical and not mq.q.numerical_answer:
            mq.q.numerical_answer, mq.answer_source = numerical, source
            applied += 1
            if not mq.q.options and mq.q.question_type == "subjective":
                mq.q.question_type = "numerical"
        if entry.explanation and (not mq.q.explanation or authoritative and len(entry.explanation) > len(mq.q.explanation)):
            mq.q.explanation = entry.explanation
        if mq.q.question_type == "mcq_single" and len(mq.q.answer) > 1:
            mq.q.question_type = "mcq_multi"
    return applied


def validate_question(mq: MergedQuestion, profile: DocumentProfile, typical_options: int | None = None) -> None:
    """Recompute structural issues for one question (keeps cross-check results)."""
    mq.issues = [
        i for i in mq.issues if " disagrees with " in i or i.startswith(("Conflicting extraction", "A numbered line"))
    ]
    q = mq.q
    expects_answers = profile.answer_location != "none"
    if len(q.text.strip()) < 8 and not mq.figures:
        mq.issues.append("Question text is empty or too short")
    if q.question_type in ("mcq_single", "mcq_multi"):
        labels = [o.label for o in q.options]
        if len(labels) < 2:
            mq.issues.append(f"Only {len(labels)} option(s) found")
        elif typical_options and len(labels) != typical_options:
            mq.issues.append(f"{len(labels)} options, but most questions in this paper have {typical_options}")
        expected = [chr(ord("A") + i) for i in range(len(labels))]
        if labels and labels != expected:
            mq.issues.append(f"Option labels look out of sequence: {', '.join(labels)}")
        if any(not o.text.strip() and o.label not in {f.option_label for f in mq.figures} for o in q.options):
            mq.issues.append("An option has neither text nor a figure")
        texts = [_plain(o.text) for o in q.options if _plain(o.text)]
        if len(texts) != len(set(texts)):
            mq.issues.append("Two options have identical text")
        if q.answer and not set(q.answer) <= set(labels):
            mq.issues.append(f"Answer {q.answer} is not one of the options")
        if expects_answers and not q.answer:
            mq.issues.append("No answer found")
    elif q.question_type == "numerical" and expects_answers and not q.numerical_answer:
        mq.issues.append("No numerical answer found")
    if _FIGURE_WORDS.search(q.text) and not mq.figures:
        mq.issues.append("Text refers to a figure but none was captured")
    if len(re.findall(r"(?<!\\)\$", q.text)) % 2:  # "\$100" is a literal dollar, not math
        mq.issues.append("Unbalanced LaTeX delimiters")
    if _INSTRUCTION_WORDS.search(q.text) and not q.options:
        mq.issues.append("Looks like exam instructions rather than a question")
    if (m := _EMBEDDED_QUESTION.search("\n" + q.text)) and norm_number(m.group(1)) != mq.key[1]:
        if int(m.group(1)) > 9 or q.options:  # small numbers are usually numbered statements
            mq.issues.append(f"Stem seems to contain another question ({m.group(1)}.)")
    if q.notes:
        mq.issues.append(f"Model note: {q.notes}")


def typical_option_count(questions: list[MergedQuestion]) -> int | None:
    counts: dict[int, int] = {}
    for mq in questions:
        if mq.q.options:
            counts[len(mq.q.options)] = counts.get(len(mq.q.options), 0) + 1
    if not counts:
        return None
    best, n = max(counts.items(), key=lambda kv: kv[1])
    return best if n >= 0.8 * sum(counts.values()) else None


def missing_numbers(questions: list[MergedQuestion], profile: DocumentProfile) -> list[tuple[str, list[int]]]:
    """Numbering gaps per section, plus questions missing after the last one when the paper states a total."""
    gaps: list[tuple[str, list[int]]] = []
    by_section: dict[str, list[int]] = {}
    for mq in questions:
        if mq.key[1].isdigit():
            by_section.setdefault(mq.key[0], []).append(int(mq.key[1]))
    for sec, numbers in by_section.items():
        present = set(numbers)
        lo = 1 if min(numbers) <= 5 else min(numbers)
        hi = max(numbers)
        if profile.total_questions and len(by_section) == 1 and not profile.numbering_restarts_per_section:
            hi = max(hi, profile.total_questions)
        missing = [n for n in range(lo, hi + 1) if n not in present]
        if missing:
            gaps.append((sec, missing))
    return gaps


def revalidate(questions: list[MergedQuestion], profile: DocumentProfile, stats: dict) -> None:
    """(Re)compute every question's issues and the document's missing numbers."""
    typical = typical_option_count(questions)
    for mq in questions:
        validate_question(mq, profile, typical)

    # Numbering gaps usually mean a question was skipped (e.g. hidden in a two-column layout).
    gaps = missing_numbers(questions, profile)
    stats["missing_numbers"] = [str(n) for _, numbers in gaps for n in numbers]
    gap_set = {(sec, n) for sec, numbers in gaps for n in numbers}
    for mq in questions:
        if not mq.key[1].isdigit():
            continue
        n = int(mq.key[1])
        before = []
        k = n - 1
        while (mq.key[0], k) in gap_set:
            before.insert(0, str(k))
            k -= 1
        if before:
            mq.issues.append(f"Question(s) {', '.join(before)} before this one were not found")
