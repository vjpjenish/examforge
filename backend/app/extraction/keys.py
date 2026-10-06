"""Deterministic answer-key and solution parsing over the (reading-ordered) text layer.

Solution PDFs are long (50+ pages) and very regular, so they are parsed with rules instead of a model:
no quota is spent, and explanations are copied verbatim, so nothing can be invented. Recognised forms:

    answer-key grids      1. (c)   11. (a)   21. (b) ...        1-c 2-a ...      Q1 c  Q2 a
    labelled blocks       Q1.  Answer: c  Explanation: ...      Q.6) Ans) a Exp) ...
    number + answer head  1. (d) Explanation: ...               Q 7. C  <explanation text>

An entry is only accepted when its number fits the running sequence, so numbered statements inside an
explanation ("1. It is a perennial ...") never start a new entry. Scanned or unusual solution PDFs fall
back to the model (see pipeline), and the coverage check below decides which path is trusted.
"""

import re
from dataclasses import dataclass, field

from app.extraction.labels import normalize_answer
from app.extraction.schemas import AnswerKeyEntry

_LETTER = r"[A-Ha-h]"
# One answer token: a letter (optionally in brackets), several letters, or a number.
_ANS = rf"\(?\s*{_LETTER}\s*\)?(?:\s*(?:,|&|and)\s*\(?\s*{_LETTER}\s*\)?)*"

# "1. (c)" / "1) c" / "Q1 - C" / "1-c" pairs; several per line in key grids.
_GRID_PAIR = re.compile(rf"(?<![\w.])(?:Q\s*\.?\s*)?(\d{{1,3}})\s*[.):\-–]?\s*\(\s*({_LETTER})\s*\)|(?<![\w.])(?:Q\s*\.?\s*)?(\d{{1,3}})\s*[.):\-–]\s*({_LETTER})(?![\w])")

# A block head: number (with Q prefix) and optionally the answer on the same line.
_HEAD = re.compile(
    rf"^\s*(?:Q(?:ues(?:tion)?)?\s*[.:]?\s*(?:No\.?)?\s*)?(\d{{1,3}})\s*[.):\-–]?\s*"
    rf"(?:(?:Ans(?:wer)?|Correct\s+(?:Answer|Option))\s*[):.\-–]*\s*)?"
    rf"(?:\(\s*({_LETTER})\s*\)|({_LETTER})(?=[\s.):]|$))?\s*[.)]?\s*(.*)$"
)
_Q_PREFIX = re.compile(r"^\s*Q(?:ues(?:tion)?)?\s*[.:]?\s*(?:No\.?)?\s*\d", re.I)
_ANSWER_LINE = re.compile(
    rf"^\s*(?:Ans(?:wer)?|Correct\s+(?:Answer|Option)|Key)\s*[):.\-–]*\s*(?:Option\s*)?({_ANS}|-?\d+(?:\.\d+)?)\s*(?:[).]\s*)?(.*)$",
    re.I,
)
_EXPLANATION_LINE = re.compile(r"^\s*(?:Exp(?:lanation)?|Sol(?:ution)?|Solution\s+&\s+Explanation)\s*[):.\-–]*\s*(.*)$", re.I)


@dataclass
class ParsedKey:
    entries: dict[int, AnswerKeyEntry] = field(default_factory=dict)
    grid_answers: dict[int, list[str]] = field(default_factory=dict)
    # First and last page (0-based) each entry's text spans.
    spans: dict[int, tuple[int, int]] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)

    def as_entries(self) -> list[AnswerKeyEntry]:
        out = []
        for n in sorted(set(self.entries) | set(self.grid_answers)):
            e = self.entries.get(n) or AnswerKeyEntry(number=str(n))
            grid = self.grid_answers.get(n)
            if grid and e.answer and grid != e.answer:
                self.conflicts.append(f"Q{n}: answer key says {grid}, explanation says {e.answer}")
            if grid and not e.answer:
                e.answer = grid
            out.append(e)
        return out

    def coverage(self, expected: int | None = None) -> float:
        numbers = set(self.entries) | set(self.grid_answers)
        if not numbers:
            return 0.0
        top = expected or max(numbers)
        return len([n for n in numbers if 1 <= n <= top]) / top


def _grid_line_pairs(line: str) -> list[tuple[int, str]]:
    pairs = []
    for m in _GRID_PAIR.finditer(line):
        num, ans = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        pairs.append((int(num), ans))
    return pairs


def _is_grid_line(line: str) -> bool:
    """A line that is nothing but number/answer pairs, e.g. '1. (c) 11. (c) 21. (c)'."""
    pairs = _grid_line_pairs(line)
    if len(pairs) < 2:
        return False
    # "(a) 1 (b) 2 (c) 3 (d) 4" is a row of options whose values are numbers, not a key.
    if re.match(r"^\s*\(?[A-Ha-h]\s*\)", line):
        return False
    numbers = [n for n, _ in pairs]
    if any(b <= a for a, b in zip(numbers, numbers[1:])):
        return False
    rest = _GRID_PAIR.sub("", line)
    return not re.search(r"[A-Za-z]{2,}", rest)


def _is_grid_debris(line: str) -> bool:
    """Pieces of a multi-column key grid split by column detection: '1. (d) 26.', '(a) 51. (a)', '26.'."""
    if re.search(r"[A-Za-z]{2,}", line):
        return False
    numbers = re.findall(r"\d{1,3}", line)
    return len(numbers) >= 2 or bool(re.fullmatch(r"\(?[A-Ha-h]\)?(\s.*)?|\d{1,3}\s*[.)]?", line))


def parse_answer_text(pages: list[str], rows: list[str] | None = None, strict: bool = False) -> ParsedKey:
    """Parse answer keys and solution blocks.

    `pages` is the reading-ordered text of each page; `rows` the same pages as full-width rows, where
    answer-key tables keep their rows intact (column detection splits a 4-column grid apart).
    `strict` is for question papers: "1. A body of mass..." is a question, not "answer A", so only key
    grids and blocks with an explicit answer marker ("Q1. Answer: c") are accepted."""
    out = ParsedKey()
    grid_pages: set[int] = set()
    for page_index, page in enumerate(rows or pages):
        for line in page.splitlines():
            if _is_grid_line(line.strip()):
                grid_pages.add(page_index)
                for n, ans in _grid_line_pairs(line):
                    out.grid_answers.setdefault(n, normalize_answer([ans]))

    current: AnswerKeyEntry | None = None
    current_n = 0
    body: list[str] = []
    page_now = 0

    def close() -> None:
        nonlocal current, body
        while body and body[-1].isdigit():
            body.pop()
        if current is not None:
            text = "\n".join(body).strip()
            if text:
                current.explanation = text
            n = int(current.number)
            if strict and not (current.answer or current.numerical_answer):
                pass  # a question in a question paper, not an answer entry
            elif n not in out.entries:  # a later duplicate block (another section) never overwrites
                out.entries[n] = current
                out.spans[n] = (current.page_offset, page_now)
        current, body = None, []

    for page_index, page in enumerate(pages):
        page_now = page_index
        if body and body[-1].isdigit():
            body.pop()  # page number at the foot of the previous page
        for raw in page.splitlines():
            line = raw.strip()
            if not line or _is_grid_line(line):
                continue
            if page_index in grid_pages and _is_grid_debris(line):
                continue

            head = _HEAD.match(line)
            if head:
                n = int(head.group(1))
                letter = head.group(2) or (None if strict else head.group(3))
                rest = head.group(4) or ""
                # A new block must continue the sequence. "Q" prefixed heads may skip numbers (a missing
                # explanation); a bare "3." inside an explanation is a numbered point, not a new entry.
                prefixed = bool(_Q_PREFIX.match(line))
                plausible = n == current_n + 1 or (prefixed and current_n < n <= current_n + 20) or (current is None and n <= 3)
                bare_head = letter is not None or not rest or _ANSWER_LINE.match(rest) or _EXPLANATION_LINE.match(rest)
                if plausible and (prefixed or bare_head):
                    close()
                    current_n = n
                    current = AnswerKeyEntry(number=str(n), page_offset=page_index)
                    if letter:
                        current.answer = normalize_answer([letter])
                    if rest:
                        if m := _ANSWER_LINE.match(rest):
                            _set_answer(current, m.group(1))
                            rest = m.group(2)
                        if m := _EXPLANATION_LINE.match(rest):
                            rest = m.group(1)
                        if rest.strip():
                            body.append(rest.strip())
                    continue

            if current is None:
                continue
            if not current.answer and not current.numerical_answer and (m := _ANSWER_LINE.match(line)):
                _set_answer(current, m.group(1))
                if m.group(2).strip():
                    body.append(m.group(2).strip())
                continue
            if not body and (m := _EXPLANATION_LINE.match(line)):
                if m.group(1).strip():
                    body.append(m.group(1).strip())
                continue
            body.append(line)
    close()
    return out


def _set_answer(entry: AnswerKeyEntry, raw: str) -> None:
    raw = raw.strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", raw):
        entry.numerical_answer = raw
    else:
        entry.answer = normalize_answer(re.split(r"\s*(?:,|&|and)\s*", raw, flags=re.I))
