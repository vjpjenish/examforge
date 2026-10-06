from app.extraction.merge import ChunkResult, merge_chunks
from app.extraction.schemas import AnswerKeyEntry, ChunkExtraction, DocumentProfile, ExtractedQuestion


def q(number, text="What is the value of x in the equation?", options="ABCD", **kw):
    return ExtractedQuestion(
        number=number,
        text=text,
        options=[{"label": label, "text": f"opt {label}"} for label in options],
        confidence=kw.pop("confidence", 0.95),
        **kw,
    )


def chunk(pages, *questions, key=()):
    return ChunkResult(pages=pages, primary_count=len(pages), output=ChunkExtraction(questions=list(questions), answer_key=list(key)))


def test_continuation_fragment_is_stitched_into_previous_question():
    profile = DocumentProfile(answer_location="none")
    first = q("1", options="AB", section="Physics")
    tail = q("1", text="", options="CD", continues_from_previous_page=True)
    merged, stats = merge_chunks([chunk([0, 1], first), chunk([1, 2], tail, q("2"))], profile)
    assert [m.q.number for m in merged] == ["1", "2"]
    assert [o.label for o in merged[0].q.options] == ["A", "B", "C", "D"]
    assert merged[1].q.section == "Physics"  # carried forward
    assert stats["continuations_stitched"] == 1


def test_duplicates_from_overlapping_windows_keep_most_complete():
    profile = DocumentProfile(answer_location="none")
    partial = q("5", options="AB")
    full = q("5", options="ABCD")
    merged, stats = merge_chunks([chunk([0, 1], partial), chunk([1, 2], full)], profile)
    assert len(merged) == 1 and len(merged[0].q.options) == 4
    assert stats["duplicates_merged"] == 1


def test_answer_key_with_restarting_numbering_is_matched_by_order():
    profile = DocumentProfile(answer_location="answer_key_at_end", numbering_restarts_per_section=True)
    qs = [q("1", section="Physics"), q("2", section="Physics"), q("1", section="Chemistry"), q("2", section="Chemistry")]
    key = [AnswerKeyEntry(number=n, answer=[a]) for n, a in [("1", "A"), ("2", "B"), ("1", "C"), ("2", "D")]]
    merged, stats = merge_chunks([chunk([0], *qs), chunk([1], key=key)], profile)
    assert [m.q.answer for m in merged] == [["A"], ["B"], ["C"], ["D"]]
    assert stats["answers_from_key"] == 4


def test_validator_flags_structural_problems():
    profile = DocumentProfile(answer_location="inline")
    merged, stats = merge_chunks(
        [chunk([0], q("1", answer=["A"]), q("3", options="A", text="As shown in the figure, find x"))], profile
    )
    assert merged[0].issues == []
    issues = " | ".join(merged[1].issues)
    assert "Only 1 option" in issues
    assert "No answer found" in issues
    assert "figure" in issues
    assert "Question(s) 2" in issues
    assert stats["missing_numbers"] == ["2"]
    assert merged[1].confidence < merged[0].confidence


def test_numeric_option_answers_are_normalised_to_letters():
    profile = DocumentProfile(answer_location="inline")
    merged, _ = merge_chunks([chunk([0], q("1", answer=["(3)"]))], profile)
    assert merged[0].q.answer == ["C"]
