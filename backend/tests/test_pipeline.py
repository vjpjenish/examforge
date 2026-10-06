"""Exercise the model-provider path (windows, cache, retries, recovery, verification) with a fake model."""

import pytest

from app.config import get_settings
from app.extraction.pipeline import ChunkCache, extract_document
from app.extraction.providers import QuotaExhausted
from app.extraction.schemas import Box, ChunkExtraction, DocumentProfile, ExtractedQuestion


class FakeModel:
    name = "fake"

    def __init__(self):
        self.windows = []
        self.focus = []
        self.verified = []
        self.calls = 0

    def profile(self, pages):
        return DocumentProfile(answer_location="inline", sections=[{"name": "Physics"}])

    def extract_chunk(self, primary, lookahead, profile, section_hint, focus=None):
        self.calls += 1
        self.windows.append(([p.index for p in primary], lookahead.index if lookahead else None))
        if focus:
            self.focus.append(focus)
            return ChunkExtraction(questions=[self._q(n, 0) for n in focus])
        return ChunkExtraction(questions=[self._q(str(primary[0].index + 1), primary[0].index)])

    def _q(self, number, first):
        return ExtractedQuestion(
            number=number,
            section="Physics",
            text=f"Refer to the figure. Find the current through R{number}.",
            options=[{"label": label, "text": f"{label} amp"} for label in "ABCD"],
            answer=["A"],
            confidence=0.9 if first else 0.5,  # the first question is doubtful and must be re-verified
            figures=[{"page_offset": 0, "box_2d": [100, 100, 400, 600]}],
        )

    def verify(self, question, pages, issues):
        self.verified.append(question.number)
        fixed = question.model_copy(deep=True)
        fixed.confidence = 0.97
        fixed.figures = [Box(page_offset=0, box_2d=[120, 100, 380, 600])]
        return fixed


def _settings(**kw):
    return get_settings().model_copy(update={"pages_per_chunk": 2, "extraction_concurrency": 1, **kw})


def test_windows_recovery_verification_and_figures(sample_pdf):
    model = FakeModel()
    stages = []
    profile, questions, stats = extract_document(str(sample_pdf), model, _settings(), lambda s, p: stages.append(s))

    # Two regular windows, then one targeted re-read for the missing question 2 between Q1 and Q3.
    assert sorted(model.windows[:2]) == [([0, 1], 2), ([2], None)]
    assert model.focus == [["2"]] and stats["recovered_numbers"] == ["2"]
    assert [q.q.number for q in questions] == ["1", "2", "3"]
    assert stats["missing_numbers"] == []
    # The fake model reads every answer as "A", but the key printed on page 3 (parsed from the text layer)
    # says B, B, C: each disagreement is flagged and sent for re-verification, never silently overwritten.
    assert [q.q.answer for q in questions] == [["A"], ["A"], ["A"]]
    assert "Answer ['A'] disagrees with answer_key ['C']" in questions[2].issues
    assert sorted(model.verified) == ["1", "2", "3"] and questions[0].q.confidence == 0.97
    assert questions[0].figures[0].box_2d == [120, 100, 380, 600]
    assert stats["chunk_errors"] == [] and stats["unprocessed_pages"] == []
    assert stages[0] == "loading" and "recovering" in stages and "verifying" in stages


def test_failed_window_is_retried(sample_pdf):
    class FlakyOnce(FakeModel):
        failed = False

        def extract_chunk(self, primary, lookahead, profile, section_hint, focus=None):
            if primary[0].index == 2 and not self.failed:
                self.failed = True
                raise RuntimeError("model overloaded")
            return super().extract_chunk(primary, lookahead, profile, section_hint, focus)

    _, questions, stats = extract_document(str(sample_pdf), FlakyOnce(), _settings(max_recover_calls=0))
    assert [q.q.number for q in questions] == ["1", "3"]
    assert stats["chunk_errors"] == [] and stats["unprocessed_pages"] == []


def test_window_that_keeps_failing_is_reported_not_hidden(sample_pdf):
    class Broken(FakeModel):
        def extract_chunk(self, primary, lookahead, profile, section_hint, focus=None):
            if primary[0].index == 2:
                raise RuntimeError("model overloaded")
            return super().extract_chunk(primary, lookahead, profile, section_hint, focus)

    _, questions, stats = extract_document(str(sample_pdf), Broken(), _settings(max_recover_calls=0))
    assert [q.q.number for q in questions] == ["1"]
    assert stats["unprocessed_pages"] == [3]
    assert stats["chunk_errors"] == ["pages 3: RuntimeError: model overloaded"]


def test_cache_resumes_after_quota_stop(sample_pdf, tmp_path):
    class OutOfQuota(FakeModel):
        def extract_chunk(self, primary, lookahead, profile, section_hint, focus=None):
            if primary[0].index == 2:
                raise QuotaExhausted("daily quota")
            return super().extract_chunk(primary, lookahead, profile, section_hint, focus)

    cache = ChunkCache(tmp_path / "cache")
    settings = _settings(max_recover_calls=0)
    _, questions, stats = extract_document(str(sample_pdf), OutOfQuota(), settings, cache=cache)
    assert [q.q.number for q in questions] == ["1"] and stats["unprocessed_pages"] == [3]

    # Next day: the finished window comes from the cache, only page 3 is sent to the model.
    model = FakeModel()
    _, questions, stats = extract_document(str(sample_pdf), model, settings, cache=cache)
    assert model.windows == [([2], None)]
    assert [q.q.number for q in questions] == ["1", "3"]


def test_quota_on_every_window_fails_the_job_with_a_clear_message(sample_pdf):
    class NoQuota(FakeModel):
        def extract_chunk(self, *a, **kw):
            raise QuotaExhausted("daily quota")

    with pytest.raises(QuotaExhausted, match="quota"):
        extract_document(str(sample_pdf), NoQuota(), _settings())


def test_profile_failure_falls_back_to_text_profile(sample_pdf):
    class NoProfile(FakeModel):
        def profile(self, pages):
            raise RuntimeError("503 overloaded")

    profile, questions, stats = extract_document(str(sample_pdf), NoProfile(), _settings(max_recover_calls=0))
    assert "profile_error" in stats and questions
    assert profile.answer_location == "answer_key_at_end"  # read from the text layer instead


def test_failed_recovery_pass_does_not_fail_the_document(sample_pdf):
    class RecoveryDown(FakeModel):
        def extract_chunk(self, primary, lookahead, profile, section_hint, focus=None):
            if focus:
                raise RuntimeError("network down")
            return super().extract_chunk(primary, lookahead, profile, section_hint, focus)

    _, questions, stats = extract_document(str(sample_pdf), RecoveryDown(), _settings())
    assert [q.q.number for q in questions] == ["1", "3"]
    assert stats["missing_numbers"] == ["2"] and "network down" in stats["recovery_error"]
