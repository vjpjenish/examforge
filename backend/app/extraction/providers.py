"""Model providers for the extraction pipeline.

`GeminiProvider` is the production engine (vision + structured output).
`HeuristicProvider` is a regex fallback over the PDF text layer: it needs no API key,
which makes it useful for local development, tests and as a degraded mode.
"""

import logging
import re
import threading
import time
from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.config import Settings
from app.extraction import prompts
from app.extraction.keys import parse_answer_text
from app.extraction.labels import clean_label
from app.extraction.pdf import PageContent
from app.extraction.schemas import (
    AnswerKeyEntry,
    ChunkExtraction,
    DocumentProfile,
    ExtractedOption,
    ExtractedQuestion,
    SolutionsExtraction,
)

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class ExtractionProvider(Protocol):
    name: str

    def profile(self, pages: list[PageContent]) -> DocumentProfile: ...

    def extract_chunk(
        self,
        primary: list[PageContent],
        lookahead: PageContent | None,
        profile: DocumentProfile,
        section_hint: str | None,
        focus: list[str] | None = None,
    ) -> ChunkExtraction: ...

    def extract_solutions(
        self, primary: list[PageContent], lookahead: PageContent | None, wanted: list[str] | None = None
    ) -> list[AnswerKeyEntry]: ...

    def verify(
        self, question: ExtractedQuestion, pages: list[PageContent], issues: list[str]
    ) -> ExtractedQuestion | None: ...


def _legend(primary: list[PageContent], lookahead: PageContent | None) -> str:
    lines = [f"- document {i}: PRIMARY page {p.index + 1}" for i, p in enumerate(primary)]
    if lookahead is not None:
        lines.append(f"- document {len(primary)}: LOOKAHEAD page {lookahead.index + 1} (context only)")
    return "\n".join(lines)


class QuotaExhausted(RuntimeError):
    """Every configured model is out of quota or unavailable."""


class GeminiProvider:
    name = "gemini"

    def __init__(self, settings: Settings):
        from google import genai  # imported lazily so the heuristic mode needs no SDK setup
        from google.genai import types

        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self.settings = settings
        # Our own retry/fallback logic decides what to do on 429/503, so the SDK must not retry silently,
        # and a hung request must not block a job forever.
        self.client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=settings.gemini_timeout_seconds * 1000, retry_options=types.HttpRetryOptions(attempts=1)
            ),
        )
        self._exhausted: set[str] = set()
        self._lock = threading.Lock()
        self.calls = 0

    # -- low level -----------------------------------------------------------------
    def _parts(self, pages: list[PageContent]) -> list:
        """One `application/pdf` part per page, labelled so `page_offset` in the schema still lines up.

        Each page goes as its own one-page PDF rather than one merged slice, because the extraction
        schema addresses pages by their position in this list (`page_offset`, and a figure's `box_2d` is
        relative to its own page). The text layer is deliberately not sent: a garbled or
        column-interleaved text layer misleads the model, which reads the PDF better unaided."""
        from google.genai import types

        parts: list = []
        for i, page in enumerate(pages):
            parts.append(f"[document {i} = page {page.index + 1}]")
            parts.append(types.Part.from_bytes(data=page.pdf, mime_type="application/pdf"))
        return parts

    def _generate(self, model: str, contents: list, schema: type[T], attempts: int = 4) -> T:
        from google.genai import errors

        chain = [m for m in dict.fromkeys([model, *self.settings.gemini_fallback_models]) if m not in self._exhausted]
        if not chain:
            raise QuotaExhausted("All Gemini models are out of quota for today")
        for i, name in enumerate(chain):
            last = i == len(chain) - 1
            try:
                # With fallbacks left, give up on a busy model quickly and move on to the next one.
                return self._generate_once(name, contents, schema, attempts if last else 2)
            except errors.APIError as exc:
                if exc.code == 429 and "PerDay" in str(exc):
                    with self._lock:
                        self._exhausted.add(name)  # daily quota is gone: skip this model for the rest of the run
                if exc.code not in (429, 503, 500, 504) or last:
                    if exc.code == 429 and "PerDay" in str(exc):
                        raise QuotaExhausted(f"Daily Gemini quota used up on every model ({name} was last)") from exc
                    raise
                log.warning("Gemini %s on %s, falling back to %s", exc.code, name, chain[i + 1])
        raise AssertionError("unreachable")

    def _generate_once(self, model: str, contents: list, schema: type[T], attempts: int) -> T:
        import httpx
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=schema,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        delay = 3.0
        model_tries = network_tries = 0
        while True:
            try:
                with self._lock:
                    self.calls += 1
                response = self.client.models.generate_content(model=model, contents=contents, config=config)
                return schema.model_validate_json(response.text or "{}")
            except errors.APIError as exc:
                model_tries += 1
                retryable = exc.code in (408, 429, 500, 502, 503, 504)
                daily_quota = exc.code == 429 and "PerDay" in str(exc)
                if not retryable or daily_quota or model_tries >= attempts:
                    raise
                wait = delay
                if exc.code == 429 and (m := re.search(r"retry in ([\d.]+)s", str(exc))):
                    wait = min(65.0, float(m.group(1)) + 1)  # per-minute limit: wait as long as the API asks
                log.warning("Gemini %s on %s (attempt %s/%s), retrying in %.0fs", exc.code, model, model_tries, attempts, wait)
            except httpx.TransportError as exc:
                # The connection dropped (DNS, Wi-Fi, timeout). Not the model's fault, and switching models
                # would not help: wait longer and try the same request again.
                network_tries += 1
                if network_tries >= 4:
                    raise
                wait = 15.0 * network_tries
                log.warning("Network error calling %s (%s); retrying in %.0fs", model, exc, wait)
            except ValueError as exc:  # malformed / truncated JSON
                model_tries += 1
                if model_tries >= attempts:
                    raise
                wait = delay
                log.warning("Unparseable Gemini output from %s (attempt %s): %s", model, model_tries, exc)
            time.sleep(wait)
            delay *= 2

    # -- pipeline steps ------------------------------------------------------------
    def profile(self, pages: list[PageContent]) -> DocumentProfile:
        # First 3 pages carry instructions/section info; a few later samples reveal the answer key layout.
        picks = pages[:3]
        if len(pages) > 3:
            step = max(1, (len(pages) - 3) // 3)
            picks += pages[3::step][:2] + pages[-1:]
        seen: set[int] = set()
        sample = [p for p in picks if not (p.index in seen or seen.add(p.index))]
        contents = [*self._parts(sample), prompts.PROFILE_PROMPT]
        return self._generate(self.settings.gemini_model, contents, DocumentProfile)

    def extract_chunk(self, primary, lookahead, profile, section_hint, focus=None):
        pages = primary + ([lookahead] if lookahead else [])
        prompt = prompts.CHUNK_PROMPT.format(
            profile=profile.model_dump_json(exclude_none=True, indent=1),
            page_legend=_legend(primary, lookahead),
            language=self.settings.extraction_language,
            section_hint=section_hint or "none seen yet",
            focus=prompts.FOCUS_PROMPT.format(numbers=", ".join(focus)) if focus else "",
        )
        return self._generate(self.settings.gemini_model, [*self._parts(pages), prompt], ChunkExtraction)

    def extract_solutions(self, primary, lookahead, wanted=None):
        pages = primary + ([lookahead] if lookahead else [])
        hint = ""
        if wanted:
            hint = f"\nThe entries most needed from these pages are for question(s): {', '.join(wanted)}.\n"
        prompt = prompts.SOLUTIONS_PROMPT.format(page_legend=_legend(primary, lookahead), wanted=hint)
        out = self._generate(self.settings.gemini_model, [*self._parts(pages), prompt], SolutionsExtraction)
        return out.entries

    def verify(self, question, pages, issues):
        prompt = prompts.VERIFY_PROMPT.format(
            question=question.model_dump_json(indent=1),
            issues="\n".join(f"- {i}" for i in issues) or "- low confidence",
            page_legend=_legend(pages, None),
        )
        return self._generate(self.settings.gemini_verify_model, [*self._parts(pages), prompt], ExtractedQuestion)


# ----------------------------------------------------------------------------------
# Offline fallback
# ----------------------------------------------------------------------------------
_Q_RE = re.compile(r"^\s*(?:Q(?:ues(?:tion)?)?\s*[.:]?\s*(?:No\.?)?\s*)?(\d{1,3})\s*[.):]\s+(.*\S)?\s*$", re.I)
# Option lines: (a) / a) / A. / (1) / 1) / (i) / i). A bare "1." is a numbered statement, not an option.
_OPT_RE = re.compile(r"^\s*(?:\(([A-Ha-h]|[1-8]|i{1,3}|iv|vi{0,3})\)|([A-Ha-h]|[1-8]|i{1,3}|iv|vi{0,3})\)|([A-Ha-h])\.)\s+(.*\S)\s*$")
_INLINE_OPTS_RE = re.compile(r"\(([A-Da-d])\)\s*(.+?)(?=\s*\([A-Da-d]\)|$)")
_ANS_RE = re.compile(r"^\s*(?:Ans(?:wer)?|Correct\s+Answer)\s*[:.\-)]?\s*\(?([A-Da-d](?:\s*,\s*[A-Da-d])*|-?\d+(?:\.\d+)?)\)?", re.I)
_SOL_RE = re.compile(r"^\s*(?:Sol(?:ution)?|Exp(?:lanation)?)\s*[:.\-)]\s*(.*)$", re.I)
_SECTION_RE = re.compile(r"^\s*(?:(?:SECTION|PART)\s*[-:]?\s*[A-Z0-9]+.*|PHYSICS|CHEMISTRY|MATHEMATICS|BIOLOGY|BOTANY|ZOOLOGY|GENERAL\s+\w+.*|REASONING.*|QUANTITATIVE\s+\w+.*|ENGLISH.*)\s*$")
_KEY_HEADER_RE = re.compile(r"^\s*ANSWER\s*KEYS?\b", re.I)
_KEY_PAIR_RE = re.compile(r"(\d{1,3})\s*[.)\-:]\s*\(?([A-Da-d]|-?\d+(?:\.\d+)?)\)?")
_TOTAL_RE = re.compile(r"contains\s+(\d{1,3})\s+(?:items|questions)", re.I)
_INSTRUCTIONS_RE = re.compile(r"\b(instructions|test booklet|answer sheet|OMR)\b", re.I)


def _option_match(line: str) -> tuple[str, str] | None:
    m = _OPT_RE.match(line)
    if not m:
        return None
    raw = m.group(1) or m.group(2) or m.group(3)
    return clean_label(raw), m.group(4)


class HeuristicProvider:
    """Regex extraction over the text layer. Accurate only for clean, conventional layouts."""

    name = "heuristic"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings

    def profile(self, pages):
        text = "\n".join(p.text for p in pages)
        sections = []
        for line in text.splitlines():
            if _SECTION_RE.match(line) and line.strip() not in [s["name"] for s in sections]:
                sections.append({"name": line.strip()})
        has_key = any(_KEY_HEADER_RE.match(line) for line in text.splitlines())
        has_inline = bool(re.search(r"^\s*Ans(?:wer)?\s*[:.]", text, re.I | re.M))
        location = "mixed" if has_key and has_inline else "answer_key_at_end" if has_key else "inline" if has_inline else "none"
        total = _TOTAL_RE.search(text)
        return DocumentProfile.model_validate(
            {"sections": sections, "answer_location": location, "total_questions": int(total.group(1)) if total else None}
        )

    def extract_chunk(self, primary, lookahead, profile, section_hint, focus=None):
        result = ChunkExtraction(page_kinds=[], current_section_at_end=section_hint)
        section = section_hint
        current: ExtractedQuestion | None = None
        last_number = 0
        field = "text"
        in_key = False
        has_options = any(_option_match(line) for p in primary for line in p.text.splitlines())

        def close():
            nonlocal current
            if current is not None:
                if not current.options and current.numerical_answer:
                    current.question_type = "numerical"
                elif len(current.answer) > 1:
                    current.question_type = "mcq_multi"
                result.questions.append(current)
            current = None

        for offset, page in enumerate(primary):
            kind = "questions"
            # Cover/instruction pages have numbered rules ("1. This booklet contains...") but no options.
            if _INSTRUCTIONS_RE.search(page.text) and not any(_option_match(line) for line in page.text.splitlines()):
                result.page_kinds.append("instructions")
                continue
            for line in page.text.splitlines():
                if not line.strip():
                    continue
                if _KEY_HEADER_RE.match(line):
                    close()
                    in_key, kind = True, "answer_key"
                    continue
                if in_key:
                    for num, ans in _KEY_PAIR_RE.findall(line):
                        is_label = ans.upper() in "ABCD"
                        result.answer_key.append(
                            AnswerKeyEntry(
                                number=num,
                                section=section if profile.numbering_restarts_per_section else None,
                                answer=[ans.upper()] if is_label else [],
                                numerical_answer=None if is_label else ans,
                            )
                        )
                    continue
                if _SECTION_RE.match(line):
                    close()
                    section = line.strip()
                    if profile.numbering_restarts_per_section:
                        last_number = 0
                    continue
                if m := _Q_RE.match(line):
                    n = int(m.group(1))
                    # Only the next number in sequence starts a question, and (in an MCQ paper) only once
                    # the current question has its options: "2. Sweden" inside Q1 is a statement.
                    in_sequence = n == last_number + 1 or (current is None and last_number == 0)
                    ready = current is None or not has_options or current.options or field in ("answer", "explanation")
                    if in_sequence and ready:
                        close()
                        last_number = n
                        current = ExtractedQuestion(
                            number=m.group(1), section=section, text=m.group(2) or "", page_offset=offset, confidence=0.6
                        )
                        field = "text"
                        continue
                if current is None:
                    continue
                if m := _ANS_RE.match(line):
                    raw = m.group(1)
                    if re.fullmatch(r"-?\d+(?:\.\d+)?", raw) and not current.options:
                        current.numerical_answer = raw
                    else:
                        current.answer = [clean_label(x) for x in raw.split(",")]
                    field = "answer"
                    continue
                if m := _SOL_RE.match(line):
                    current.explanation = m.group(1)
                    field = "explanation"
                    continue
                if field in ("text", "option") and (inline := _INLINE_OPTS_RE.findall(line)) and len(inline) >= 2:
                    current.options += [ExtractedOption(label=lab.upper(), text=t.strip()) for lab, t in inline]
                    field = "option"
                    continue
                if field in ("text", "option") and (opt := _option_match(line)):
                    current.options.append(ExtractedOption(label=opt[0], text=opt[1]))
                    field = "option"
                    continue
                if field == "text":
                    current.text = f"{current.text}\n{line.strip()}".strip()
                elif field == "option" and current.options:
                    current.options[-1].text += " " + line.strip()
                elif field == "explanation":
                    current.explanation = f"{current.explanation or ''}\n{line.strip()}".strip()
            result.page_kinds.append(kind)
        close()
        result.current_section_at_end = section
        return result

    def extract_solutions(self, primary, lookahead, wanted=None):
        parsed = parse_answer_text([p.text for p in primary], [p.rows for p in primary])
        entries = parsed.as_entries()
        for e in entries:
            e.page_offset = parsed.spans.get(int(e.number), (0, 0))[0]
        return entries

    def verify(self, question, pages, issues):
        return None


def build_provider(settings: Settings) -> ExtractionProvider:
    if settings.extraction_provider == "heuristic":
        return HeuristicProvider(settings)
    return GeminiProvider(settings)
