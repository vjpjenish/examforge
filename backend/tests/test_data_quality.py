"""Guards for two data-quality problems found in the live PYQ bank."""

from app.extraction.keys import parse_answer_text
from app.extraction.labels import ordered_options


class TestOptionOrder:
    """402 of 2137 live questions stored their options out of label order (A, C, D, B).

    The model returns them in the reading order it found them, which on two-column papers is not
    label order, and the UI rendered them faithfully. Ordering happens on read, so questions
    already in the database are fixed without a migration.
    """

    def test_reading_order_is_sorted_into_label_order(self):
        got = ordered_options([{"label": "A"}, {"label": "C"}, {"label": "D"}, {"label": "B"}])
        assert [o["label"] for o in got] == ["A", "B", "C", "D"]

    def test_numeric_labels_are_ordered_too(self):
        got = ordered_options([{"label": "3"}, {"label": "1"}, {"label": "2"}])
        assert [o["label"] for o in got] == ["1", "2", "3"]

    def test_text_travels_with_its_label(self):
        got = ordered_options([{"label": "C", "text": "Argon"}, {"label": "A", "text": "Nitrogen"}])
        assert got == [{"label": "A", "text": "Nitrogen"}, {"label": "C", "text": "Argon"}]

    def test_unusual_labels_are_left_exactly_as_extracted(self):
        """Never guess: duplicates and phrase labels keep the order the paper had."""
        odd = [{"label": "Both A and B"}, {"label": "A"}]
        assert ordered_options(odd) == odd
        dupes = [{"label": "A"}, {"label": "A"}]
        assert ordered_options(dupes) == dupes

    def test_empty_is_safe(self):
        assert ordered_options([]) == []
        assert ordered_options(None) == []


class TestOverlongExplanations:
    """18 live questions carried explanations up to 1.28 MB -- the whole solution booklet.

    When the parser stops recognising entry boundaries, every remaining page is appended to the
    last open entry, so a monoclonal-antibodies question was showing an explanation about
    nitrogen-fixing plants. That is a parse failure, not an explanation.
    """

    def test_a_normal_explanation_is_kept(self):
        parsed = parse_answer_text(["1. (a) Explanation: short and sane.\n2. (b) Explanation: also fine.\n"])
        assert parsed.entries[1].explanation == "short and sane."
        assert parsed.entries[2].explanation == "also fine."
        assert parsed.overlong == []

    def test_a_run_on_explanation_is_dropped_and_reported(self):
        parsed = parse_answer_text(["1. (a) Explanation: " + ("filler text " * 6000)])
        assert parsed.overlong == [1], "the failure must be reported, not silent"
        assert not parsed.entries[1].explanation, "a whole booklet must not be stored as one explanation"
        assert parsed.entries[1].answer == ["A"], "the answer itself is still trustworthy"
