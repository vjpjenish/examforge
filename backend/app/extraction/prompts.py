PROFILE_PROMPT = """\
You are analysing an exam paper / test series PDF before question extraction.
You are given the first pages and a sample of later pages, each as a one-page PDF labelled with its page number.

Work out the FORMAT of this document so a later step can extract every question accurately:
- document_type: a question paper (questions, maybe with answers), or only solutions / an answer key;
- total_questions if the instructions state it (e.g. "This Test Booklet contains 100 items");
- exam name, institution/coaching brand, year, languages (bilingual Hindi/English papers are common);
- layout (single or two column), how questions are numbered and how options are labelled;
- whether numbering restarts in each section;
- every section/part with its subject and question number range, from the instructions or headings;
- where answers live: printed inline after each question, an answer key at the end, a separate
  solutions section, a mix, or nowhere;
- marking scheme and duration if the instructions state them (negative marks as negative numbers);
- anything unusual (questions spanning pages, matrix-match, assertion-reason, passages/comprehension).

Only report what you can see. Do not guess the year, exam or totals if they are not printed.
"""

_FIDELITY_RULES = """\
Absolute rules:
- Never invent, complete, correct, summarise or translate anything. Transcribe exactly what is printed,
  in the language it is printed in. If something is illegible, keep what you can read and say so in notes.
- Never solve a question. Answers and explanations come only from what the PDF prints.
"""

CHUNK_PROMPT = """\
You are an expert exam-paper transcriber. Extract every question from the PRIMARY pages below
into the JSON schema, with perfect fidelity.

Document profile (inferred earlier, may be imperfect):
{profile}

Pages in this request (each is a one-page PDF):
{page_legend}

""" + _FIDELITY_RULES + """
Rules:
1. Extract only questions that START on a primary page. If the first primary page opens with the tail
   of a question that began earlier, emit it with continues_from_previous_page=true and only the text
   you can see. Use the LOOKAHEAD page solely to finish a question that runs past the last primary page;
   never emit questions that start on the lookahead page.
2. Follow true reading order. For two-column layouts read the full left column, then the right column,
   and keep each question with its own options: never pair a stem with options from the other column.
3. A question is a numbered item in the paper's question sequence. Numbered statements, list items,
   pairs, assertion/reason lines and table rows INSIDE a question ("1. Norway", "2. Sweden", "Statement-I")
   belong to that question's stem: write them as lines of the stem, never as separate questions.
   Question numbers increase through the paper; a smaller number in the middle of a question is a statement.
4. Never extract cover pages, instructions, headers, footers, page numbers, watermarks, advertisements,
   tables of contents or answer-sheet directions as questions. Classify each primary page in page_kinds.
5. Transcribe text exactly: keep wording, units, numbers and punctuation. Write math and chemistry in
   LaTeX ($x^2$, $\\frac{{a}}{{b}}$, $H_2O$). Use Markdown tables for tabular data, one line per statement.
6. Bilingual papers (the same question printed twice, e.g. Hindi and English): keep only the {language}
   version of each question and its options. A paper in a single language (Hindi, English or any other)
   is transcribed as printed; never translate. Keep mixed-language text as it is.
7. Normalise option labels to A, B, C, D... in printed order, whatever the original style ((a), A., 1),
   (i), etc.). Keep the option text itself exact.
8. question_type: mcq_single (one correct option), mcq_multi (paper says one or more correct),
   numerical (integer/decimal answer, no options), subjective (anything else).
9. Answers: fill answer / numerical_answer / explanation ONLY when printed (inline, ticked, highlighted,
   or in an answer key / solution on these pages). Copy explanations verbatim and completely.
10. If a page is an answer key or solutions page, put each entry in answer_key (number, section if the key
    is split by section, answer labels as printed, numerical answer, verbatim explanation).
11. Figures: for every diagram, graph, map, circuit, structure or image that is part of a question or
    option, give a tight box_2d [ymin, xmin, ymax, xmax] on the 0-1000 scale of the page it is on
    (page_offset). Do not box plain text.
12. section: the section heading in force for the question (carry it over from the profile or an earlier
    heading: {section_hint}). Use the exact heading text. year: only if printed with the question.
13. confidence: lower it for illegible scans, unsure reading order, ambiguous answers or cut-off text and
    say why in notes.
{focus}"""

FOCUS_PROMPT = """
IMPORTANT: an earlier pass did not find question(s) {numbers} although the numbering suggests they are
on these pages. Look very carefully (columns, page ends, boxed or small text) and extract them if they are
printed here. Extract all other questions on the primary pages as usual. Do not create a question that is
not printed.
"""

SOLUTIONS_PROMPT = """\
You are transcribing the ANSWER KEY / SOLUTIONS pages of an exam paper. Return one entry per question
whose answer or explanation STARTS on a primary page.

Pages in this request (each is a one-page PDF):
{page_legend}

""" + _FIDELITY_RULES + """
Rules:
1. number: the question number the entry is for, as printed.
2. answer: the correct option label(s) exactly as printed (a, b, c, d / A-D / 1-4). numerical_answer for
   numeric answers. Leave empty if no answer is printed for that question.
3. explanation: the complete explanation text for that question, copied verbatim in reading order
   (bullets as "- " lines, tables as Markdown). If it continues onto the LOOKAHEAD page, include the
   continuation up to the next question's entry. Do not include text belonging to another question.
4. If the first primary page begins with the end of an explanation that started earlier, ignore it.
5. Ignore page headers, footers, watermarks and advertisements. Keep everything the paper prints as part
   of a question's solution, including boxes such as "Knowledge Box", "Relevance" or "Source".
6. page_offset: index of the page where the entry starts.
{wanted}"""

VERIFY_PROMPT = """\
You are auditing an automatically extracted exam question against its original pages (one-page PDFs).

Extracted question (JSON):
{question}

Problems detected by the validator:
{issues}

Compare carefully with the pages and return the corrected question in the same schema. Fix any
transcription mistakes, missing or merged options, wrong option labels, broken LaTeX, missing figures
(add box_2d for them), numbered statements that are missing from the stem, and a wrong question_type.
Fill answer/explanation only if they are printed on these pages. Never invent, solve or translate.
If the extraction is already correct, return it unchanged. Set confidence to reflect the final result.
Page legend: {page_legend}
"""
