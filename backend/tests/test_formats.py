"""Format coverage for the extraction engine, on synthetic PDFs (no model, no quota).

Covers: two-column reading order, running headers/footers, instructions pages, numbered statements,
questions that continue on the next page, option styles (a) / A. / (1) / inline, Hindi, answer keys at
the end, separate solution PDFs in several layouts, multi-page explanations, scanned pages, and the
merge rules that keep content from being invented, split or lost.
"""

from pathlib import Path

import pymupdf
import pytest

from app.extraction.keys import parse_answer_text
from app.extraction.labels import clean_label, normalize_answer
from app.extraction.merge import ChunkResult, merge_chunks
from app.extraction.pdf import load_pages
from app.extraction.pipeline import extract_solutions_document
from app.extraction.schemas import AnswerKeyEntry, ChunkExtraction, DocumentProfile, ExtractedQuestion
from app.worker import claim_next, process

HINDI_FONT = Path(r"C:\Windows\Fonts\Nirmala.ttc")
for candidate in ("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf", "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf"):
    if not HINDI_FONT.exists() and Path(candidate).exists():
        HINDI_FONT = Path(candidate)


def _write(page, x, y, text, size=10):
    if any("\u0900" <= ch <= "\u097f" for ch in text):
        if not HINDI_FONT.exists():
            pytest.skip("no Devanagari font on this machine")
        page.insert_font(fontname="hi", fontfile=str(HINDI_FONT))
        page.insert_text((x, y), text, fontname="hi", fontsize=size)
    else:
        page.insert_text((x, y), text, fontsize=size)


def make_paper(path: Path, pages: list[dict], header="ACME IAS ACADEMY", footer=True) -> Path:
    """pages: {"left": [...], "right": [...]} for two columns, or {"lines": [...]} for one column."""
    doc = pymupdf.open()
    for n, spec in enumerate(pages, 1):
        page = doc.new_page()
        if header:
            _write(page, 230, 30, header, 11)
        if footer:
            _write(page, 270, 815, f"Page {n} of {len(pages)}", 9)
        for col, x in (("lines", 50), ("left", 50), ("right", 310)):
            for i, line in enumerate(spec.get(col, [])):
                _write(page, x, 80 + 15 * i, line)
    doc.save(path)
    return path


PAPER = [
    {
        "lines": [
            "TEST BOOKLET - GENERAL STUDIES",
            "INSTRUCTIONS",
            "1. This Test Booklet contains 6 items (questions).",
            "2. Each item carries 2 marks. Mark answers on the OMR Answer Sheet.",
            "3. Do not open this booklet until you are told to do so.",
        ]
    },
    {
        "left": [
            "1. Consider the following countries:",
            "1. Norway",
            "2. Sweden",
            "3. Finland",
            "How many of the above are Nordic",
            "countries?",
            "(a) Only one",
            "(b) Only two",
            "(c) All three",
            "(d) None",
            "2. Which one of the following is a",
            "noble gas?",
            "A. Nitrogen",
            "B. Argon",
            "C. Oxygen",
            "D. Hydrogen",
        ],
        "right": [
            "3. Select the correct match:",
            "(1) Ozone - O3",
            "(2) Water - H2O2",
            "(3) Salt - NaCl2",
            "(4) None of these",
            "4. With reference to the Indian",
            "Constitution, consider the following",
            "statements:",
            "1. Article 21 protects life and liberty.",
            "2. Article 32 gives constitutional remedies.",
        ],
    },
    {
        "lines": [
            "Which of the statements given above is/are correct?",
            "(a) 1 only",
            "(b) 2 only",
            "(c) Both 1 and 2",
            "(d) Neither 1 nor 2",
            "5. भारत की राजधानी क्या है?",
            "(a) मुंबई",
            "(b) नई दिल्ली",
            "(c) कोलकाता",
            "(d) चेन्नई",
            "6. What is the value of 2 + 2?",
            "(a) 3 (b) 4 (c) 5 (d) 6",
            "ANSWER KEY",
            "1. (b) 2. (b) 3. (a) 4. (c) 5. (b) 6. (b)",
        ]
    },
]


# --- page text ------------------------------------------------------------------------------
def test_two_column_reading_order_and_running_headers(tmp_path):
    pages = load_pages(make_paper(tmp_path / "p.pdf", PAPER))
    text = pages[1].text
    # Left column fully before the right column, lines not interleaved.
    assert text.index("D. Hydrogen") < text.index("3. Select the correct match:")
    assert "countries?\n(a) Only one" in text
    # Repeated header and page footer are removed (and recorded); content is untouched.
    assert all("ACME IAS ACADEMY" not in p.text for p in pages)
    assert pages[0].removed == ["ACME IAS ACADEMY", "Page 1 of 3"]
    assert all(not p.text_incomplete for p in pages)


def test_repeated_option_lines_at_page_bottom_are_never_stripped(tmp_path):
    spec = [{"lines": [f"{n}. Question {n} text here?"] + [""] * 46 + ["(d) 1, 2 and 3"]} for n in range(1, 5)]
    pages = load_pages(make_paper(tmp_path / "p.pdf", spec, header=None, footer=False))
    assert all(p.text.endswith("(d) 1, 2 and 3") for p in pages)


def test_pages_are_sent_as_one_page_pdfs(tmp_path):
    """Each page goes to the model as a standalone PDF of exactly that page, text layer intact."""
    pages = load_pages(make_paper(tmp_path / "p.pdf", PAPER))
    for page in pages:
        assert page.pdf.startswith(b"%PDF")
        with pymupdf.open(stream=page.pdf, filetype="pdf") as slice_:
            assert slice_.page_count == 1
            # The vectors survive the cut, so the model reads the real page, not a raster of it.
            assert slice_[0].get_text().strip()
    with pymupdf.open(stream=pages[1].pdf, filetype="pdf") as slice_:
        assert "Hydrogen" in slice_[0].get_text()


def test_scanned_page_is_detected(tmp_path):
    src = make_paper(tmp_path / "src.pdf", [PAPER[1]], header=None, footer=False)
    png = pymupdf.open(src)[0].get_pixmap(dpi=100).tobytes("png")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=png)  # a scan: the whole page is one picture
    _write(page, 50, 40, "Scanned by CamScanner on the 2nd of October")  # but a little real text
    doc.save(tmp_path / "scan.pdf")
    (scan,) = load_pages(tmp_path / "scan.pdf")
    assert scan.text_incomplete and scan.text_coverage < 0.5


# --- labels -------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,label", [("(a)", "A"), ("b)", "B"), ("C.", "C"), (" Option d ", "D"), ("(iii)", "C"), ("iv", "D"), ("(2)", "2")]
)
def test_option_labels_are_normalised(raw, label):
    assert clean_label(raw) == label


def test_answers_map_numbers_to_letters_only_for_lettered_options():
    assert normalize_answer(["(3)"], ["A", "B", "C", "D"]) == ["C"]
    assert normalize_answer(["c", "(a)"]) == ["A", "C"]
    assert normalize_answer(["3"], ["1", "2", "3", "4"]) == ["3"]


# --- answer keys and solutions (text layer) ----------------------------------------------------
def _parse(*pages, strict=False):
    return parse_answer_text(list(pages), strict=strict)


def test_key_grid_and_labelled_blocks():
    parsed = _parse(
        "Answer Key\n1. (c) 2. (b) 3. (a)\nQ1.\nAnswer: c\nExplanation:\nNordic countries are five.\n"
        "1. Norway is one of them.\n2. Sweden is another.\nQ2.\nAnswer: b\nExplanation: Argon is inert.",
        "Q3.\nAnswer: a\nExplanation:\nThe explanation starts here",
    )
    entries = {e.number: e for e in parsed.as_entries()}
    assert [entries[n].answer for n in "123"] == [["C"], ["B"], ["A"]]
    # Numbered points inside an explanation stay in it (they are not new entries).
    assert entries["1"].explanation == "Nordic countries are five.\n1. Norway is one of them.\n2. Sweden is another."
    assert entries["2"].explanation == "Argon is inert."
    assert parsed.spans[3] == (1, 1)


@pytest.mark.parametrize(
    "text",
    [
        "Q.1) \nAns) c\nExp) Because.\nQ.2)\nAns) a\nExp) Since.",  # Forum IAS style
        "Q 1. C Because.\nQ 2. A Since.",  # Vision IAS style: answer on the number line
        "1. (c)\nExplanation:\nBecause.\n2. (a)\nExplanation:\nSince.",  # Drishti style
        "Question 1\nCorrect Answer: (c)\nSolution: Because.\nQuestion 2\nCorrect Answer: (a)\nSolution: Since.",
    ],
)
def test_solution_layouts(text):
    entries = {e.number: e for e in _parse(text).as_entries()}
    assert entries["1"].answer == ["C"] and entries["1"].explanation == "Because."
    assert entries["2"].answer == ["A"] and entries["2"].explanation == "Since."


def test_explanation_continues_across_pages_and_drops_page_numbers():
    parsed = _parse("Q1. Answer: a\nExplanation: First part\n7", "second part.\nQ2. Answer: b\nExplanation: Next.")
    entries = {e.number: e for e in parsed.as_entries()}
    assert entries["1"].explanation == "First part\nsecond part."
    assert parsed.spans[1] == (0, 1)


def test_four_column_key_grid_is_read_from_rows():
    rows = "ANSWERS\n1. (d) 3. (b) 5. (a) 7. (c)\n2. (c) 4. (a) 6. (d) 8. (b)"
    split_by_columns = "ANSWERS\n1. (d) 3.\n2. (c) 4.\n(b) 5. (a) 7. (c)\n(a) 6. (d) 8. (b)"
    parsed = parse_answer_text([split_by_columns], [rows])
    assert {e.number: e.answer[0] for e in parsed.as_entries()} == dict(zip("12345678", "DCBAADCB"))
    assert all(not e.explanation for e in parsed.as_entries())


def test_conflicting_grid_and_explanation_answers_are_reported():
    parsed = _parse("1. (a) 2. (b)\nQ1. Answer: c\nExplanation: x")
    parsed.as_entries()
    assert parsed.conflicts == ["Q1: answer key says ['A'], explanation says ['C']"]


def test_question_papers_never_yield_answers_from_question_text():
    paper = (
        "1. A body of mass 2 kg moves with velocity 3 m/s.\n(a) 6 J (b) 9 J (c) 12 J (d) 18 J\n"
        "2. How many of the above are correct?\n(a) 1 (b) 2 (c) 3 (d) 4\n"
        "Q.3) In the context of polity, consider:\n(a) x\n(b) y"
    )
    parsed = _parse(paper, strict=True)
    assert parsed.as_entries() == []


# --- merge rules -------------------------------------------------------------------------------
def _q(number, text, options="ABCD", **kw):
    return ExtractedQuestion(
        number=number, text=text, options=[{"label": c, "text": f"opt {c}"} for c in options], confidence=0.9, **kw
    )


def _chunk(pages, *qs, key=()):
    return ChunkResult(pages=pages, primary_count=len(pages), output=ChunkExtraction(questions=list(qs), answer_key=list(key)))


def test_numbered_statements_split_off_by_a_model_are_folded_back():
    profile = DocumentProfile(answer_location="none")
    q1 = _q("1", "Consider the following countries:\n1. Norway\n2. Sweden\nHow many are Nordic?")
    stray = _q("2", "Sweden", options="")  # the model mistook statement 2 for question 2
    q2 = _q("2", "Which one of the following is a noble gas?")
    merged, stats = merge_chunks([_chunk([0], q1, stray), _chunk([1], q2)], profile)
    assert [m.q.number for m in merged] == ["1", "2"]
    assert merged[1].q.text.startswith("Which one")
    assert stats["statement_fragments_folded"] == 1 and stats["conflicts"] == []


def test_two_different_questions_with_one_number_are_reported_not_dropped():
    profile = DocumentProfile(answer_location="none")
    a = _q("7", "The capital of France is")
    b = _q("7", "Photosynthesis takes place in which organelle of the plant cell?")
    merged, stats = merge_chunks([_chunk([0], a), _chunk([3], b)], profile)
    assert len(merged) == 1 and len(stats["conflicts"]) == 1
    assert "Conflicting extraction for Q7" in merged[0].issues[0]


def test_unknown_answers_stay_unknown_and_disagreements_are_flagged():
    profile = DocumentProfile(answer_location="answer_key_at_end")
    q1, q2 = _q("1", "First question text?"), _q("2", "Second question text?", answer=["A"])
    key = [AnswerKeyEntry(number="2", answer=["c"]), AnswerKeyEntry(number="3", answer=["b"])]
    merged, stats = merge_chunks([_chunk([0], q1, q2, key=key)], profile)
    assert merged[0].q.answer == [] and "No answer found" in merged[0].issues  # nothing invented
    assert merged[1].q.answer == ["A"] and "Answer ['A'] disagrees with answer_key ['C']" in merged[1].issues


def test_expected_total_reveals_missing_questions_at_the_end():
    profile = DocumentProfile(answer_location="none", total_questions=5)
    merged, stats = merge_chunks([_chunk([0], _q("1", "First question?"), _q("2", "Second question?"))], profile)
    assert stats["missing_numbers"] == ["3", "4", "5"]


def test_hindi_duplicates_from_overlapping_windows_merge():
    profile = DocumentProfile(answer_location="none")
    a = _q("5", "भारत की राजधानी क्या है?", options="AB")
    b = _q("5", "भारत की राजधानी क्या है?", options="ABCD")
    merged, stats = merge_chunks([_chunk([0, 1], a), _chunk([1, 2], b)], profile)
    assert len(merged) == 1 and len(merged[0].q.options) == 4 and stats["duplicates_merged"] == 1


# --- end to end (offline extractor) --------------------------------------------------------------
def _upload(client, headers, path: Path, title: str, kind: str, **extra):
    with open(path, "rb") as f:
        r = client.post(
            "/api/documents",
            data={"title": title, "kind": kind, **extra},
            files={"file": (path.name, f, "application/pdf")},
            headers=headers,
        )
    assert r.status_code == 200, r.text
    process(claim_next())
    return client.get(f"/api/documents/{r.json()['id']}", headers=headers).json()


def test_paper_end_to_end(client, admin_headers, tmp_path):
    doc = _upload(client, admin_headers, make_paper(tmp_path / "acme-qp.pdf", PAPER), "ACME Test 1 QP", "test_series")
    stats = doc["latest_job"]["stats"]
    qs = client.get(f"/api/documents/{doc['id']}/questions", headers=admin_headers).json()

    # Instructions are not questions; all six are found, in order, with nothing missing.
    assert [q["number"] for q in qs] == ["1", "2", "3", "4", "5", "6"]
    assert stats["missing_numbers"] == []
    # Numbered statements stay inside their question.
    assert "1. Norway\n2. Sweden\n3. Finland" in qs[0]["text"]
    assert [o["text"] for o in qs[0]["options"]] == ["Only one", "Only two", "All three", "None"]
    # Option styles A. / (1) / inline all end up as A-D.
    assert [o["text"] for o in qs[1]["options"]] == ["Nitrogen", "Argon", "Oxygen", "Hydrogen"]
    assert [o["label"] for o in qs[2]["options"]] == ["A", "B", "C", "D"]
    assert [o["text"] for o in qs[5]["options"]] == ["3", "4", "5", "6"]
    # A question that continues on the next page is reconstructed.
    assert "2. Article 32 gives constitutional remedies.\nWhich of the statements" in qs[3]["text"]
    assert len(qs[3]["options"]) == 4
    # Hindi stays Hindi.
    assert qs[4]["text"] == "भारत की राजधानी क्या है?" and qs[4]["options"][1]["text"] == "नई दिल्ली"
    # Answer key at the end, matched after label normalisation.
    assert [q["answer"] for q in qs] == [["B"], ["B"], ["A"], ["C"], ["B"], ["B"]]
    assert all(q["answer_source"] == "answer_key" for q in qs)
    assert doc["test_id"] and all(q["review_status"] == "approved" for q in qs)


SOLUTIONS = [
    {
        "lines": [
            "ACME Test 1 - Answers & Explanations",
            "1. (b) 2. (b) 3. (a) 4. (c) 5. (b) 6. (c)",
            "Q1.",
            "Answer: b",
            "Explanation:",
            "Norway and Sweden are Nordic; Finland is too.",
            "1. Norway is a Nordic country.",
            "2. Sweden is a Nordic country.",
            "Q2.",
            "Answer: b",
            "Explanation: Argon is a noble gas.",
            "Q.3)",
            "Ans) a",
            "Exp) Ozone is O3. This explanation",
        ]
    },
    {
        "lines": [
            "continues on the next page.",
            "4. (c)",
            "Explanation:",
            "Both statements are correct.",
            "Q 5. B नई दिल्ली भारत की राजधानी है।",
            "Q 6. C The sum is 4, so option (b) is right.",
        ]
    },
]


def test_separate_solutions_pdf_is_paired_and_applied(client, admin_headers, tmp_path):
    paper = _upload(client, admin_headers, make_paper(tmp_path / "qp.pdf", PAPER), "ACME Mock 7 QP", "test_series")
    sol = _upload(
        client, admin_headers, make_paper(tmp_path / "sol.pdf", SOLUTIONS, footer=False), "ACME Mock 7 Solutions", "solutions"
    )
    assert sol["solutions_for_id"] == paper["id"]  # paired by title
    stats = sol["latest_job"]["stats"]
    assert stats["entries"] == 6 and stats["missing"] == [] and stats["gemini_calls"] == 0
    assert stats["conflicts"] == []  # the grid and the explanation blocks agree

    qs = client.get(f"/api/documents/{paper['id']}/questions", headers=admin_headers).json()
    assert qs[0]["explanation"] == "Norway and Sweden are Nordic; Finland is too.\n1. Norway is a Nordic country.\n2. Sweden is a Nordic country."
    assert qs[2]["explanation"] == "Ozone is O3. This explanation\ncontinues on the next page."
    assert qs[3]["explanation"] == "Both statements are correct."
    assert qs[4]["explanation"] == "नई दिल्ली भारत की राजधानी है।"
    # The paper's own key says (b) for Q6, the solutions say C: kept, and flagged for people to check.
    assert qs[5]["answer"] == ["B"] and any("disagrees with solutions" in i for i in qs[5]["issues"])
    detail = client.get(f"/api/documents/{paper['id']}", headers=admin_headers).json()
    assert detail["solutions"][0]["id"] == sol["id"]


def test_solutions_upload_needs_a_paper(client, admin_headers, tmp_path):
    path = make_paper(tmp_path / "orphan.pdf", SOLUTIONS)
    with open(path, "rb") as f:
        r = client.post(
            "/api/documents",
            data={"title": "Completely unrelated answers", "kind": "solutions"},
            files={"file": ("orphan.pdf", f, "application/pdf")},
            headers=admin_headers,
        )
    assert r.status_code == 400


class FakeVision:
    """Reads 'page images': returns the entries printed on rasterised page 2 of the test PDF."""

    name = "fake"

    def __init__(self):
        self.pages_read = []
        self.calls = 0

    def extract_solutions(self, primary, lookahead, wanted=None):
        self.calls += 1
        self.pages_read.append([p.index for p in primary])
        out = []
        if any(p.index == 1 for p in primary):
            offset = [p.index for p in primary].index(1)
            out = [
                AnswerKeyEntry(number="2", answer=["b"], explanation="Two: full text read from the image.", page_offset=offset),
                AnswerKeyEntry(number="3", answer=["d"], explanation="Three.", page_offset=offset),
            ]
        return out


def test_solution_pages_without_usable_text_are_read_from_the_image(tmp_path):
    # Page 2's text exists only as pixels (like a PDF with broken fonts or a scan).
    image_page = make_paper(tmp_path / "img.pdf", [{"lines": ["continued from Q2 text.", "Q3.", "Answer: d", "Explanation: Three."]}], header=None, footer=False)
    png = pymupdf.open(image_page)[0].get_pixmap(dpi=110).tobytes("png")
    doc = pymupdf.open(make_paper(tmp_path / "p1.pdf", [{"lines": ["Q1.", "Answer: a", "Explanation: One.", "Q2.", "Answer: b", "Explanation: Two starts"]}], header=None, footer=False))
    page = doc.new_page()
    page.insert_image(page.rect, stream=png)
    doc.save(tmp_path / "sol.pdf")

    model = FakeVision()
    from app.config import get_settings

    entries, stats = extract_solutions_document(str(tmp_path / "sol.pdf"), model, get_settings(), expected_numbers=["1", "2", "3"])
    by_number = {e["number"]: e for e in entries}
    assert by_number["1"]["source"] == "text" and by_number["1"]["explanation"] == "One."
    # Q2's text-layer entry runs into the unreadable page, so the page image wins; Q3 exists only there.
    assert by_number["2"]["source"] == "vision" and by_number["2"]["explanation"] == "Two: full text read from the image."
    assert by_number["3"]["answer"] == ["D"] and stats["missing"] == []
    assert stats["incomplete_text_pages"] == [2] and any(1 in pages for pages in model.pages_read)
