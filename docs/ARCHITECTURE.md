# Architecture

## System

```
 Browser (Next.js, client-rendered pages, JWT in localStorage)
     │  REST/JSON
     ▼
 FastAPI (stateless; scale horizontally)
     │                         ┌─────────────────────────────┐
     ├── PostgreSQL ◀──────────┤ extraction_jobs (queue)      │
     │                         └──────────────┬──────────────┘
     └── Storage (PDFs, figures)              │ SKIP LOCKED
                                              ▼
                               Extraction workers × N ──▶ Gemini API
```

No broker is needed: the job table *is* the queue. Workers poll, claim a job atomically, and write
progress (`stage`, `progress`) back to the row, which the admin UI polls. Jobs abandoned by a crashed
worker are re-queued after an hour.

## Data model

```
Exam ──┬── Document (PDF: kind test_series|pyq, institution, year, inferred profile)
       │      ├── ExtractionJob (status, stage, progress, stats)
       │      └── Question (number, section, subject, topic, type, text, options[], answer,
       │                    explanation, images[], source_pages[], confidence, issues[], review_status)
       └── Test (duration, marking scheme) ── TestQuestion (order, section, per-question marks)
                 └── Attempt (deadline_at, score, summary) ── AttemptAnswer (response, time, visits, mark)
User ── PyqProgress (solved, is_correct, bookmarked) ── Question
```

- Questions belong to a document and an exam, so one bank serves many exams, institutes and series.
  Tests reference questions; a question can appear in several tests.
- `answer` is a JSON list of option labels for MCQs, or `{value, tolerance}` for numerical questions
  (ranges like "2.5 to 2.7" become a midpoint and tolerance).
- `summary` on an attempt caches the analytics at submit time so dashboards stay cheap.
- Indexes cover the hot paths: questions by (exam, subject), by (document, order), review status, year.

## Extraction engine (`backend/app/extraction`)

| File | Role |
| --- | --- |
| `pdf.py` | Cut pages into one-page PDFs (what the model reads), read the text layer for the key parser, crop figures from `[ymin, xmin, ymax, xmax]` 0–1000 boxes |
| `schemas.py` | Pydantic contracts used as Gemini `response_schema` (structured output) |
| `prompts.py` | Profile, chunk-extraction and verification prompts |
| `providers.py` | `GeminiProvider` (vision + JSON, retries with backoff) and offline `HeuristicProvider` |
| `merge.py` | Stitching, de-duplication, answer-key joining, normalisation, validation |
| `pipeline.py` | Orchestration, parallelism, verification pass, persistence |

Why it stays accurate on unfamiliar formats:

1. **Format first, content second.** The profile pass tells every later call how this particular paper
   numbers questions, labels options, splits sections and where its answers live.
2. **Two views of each page.** The image is authoritative for reading order, columns, math and figures;
   the text layer supplies exact characters for digital PDFs. Scanned pages fall back to vision alone.
3. **Small windows with lookahead.** Short contexts keep transcription precise; the lookahead page lets a
   window finish a question that spills over, and the next window marks the spill-over as a continuation.
4. **Schema-constrained output.** The model cannot invent shapes; labels are normalised to A–D afterwards.
5. **Independent cross-checks.** Inline answers are compared with the answer key, option sets with
   their expected sequence, numbering with its expected continuity, figure references with captured
   figures.
6. **Targeted second opinion.** Only flagged questions pay for the stronger model, which audits the
   extraction against the page images.
7. **Human in the loop.** Whatever is still doubtful is shown first to an admin, with the issues and the
   source page.

Tuning knobs (env): `PAGES_PER_CHUNK`, `EXTRACTION_CONCURRENCY`, `RENDER_DPI`, `GEMINI_MODEL`,
`GEMINI_VERIFY_MODEL`, `MAX_VERIFY_CALLS`, `REVIEW_CONFIDENCE_THRESHOLD`, `EXTRACTION_LANGUAGE`.

## Test engine

- The server owns time: `deadline_at` is set at start; answers after `deadline + 20 s` are rejected and
  any read of an expired attempt finalises it. The client clock is only a display, corrected by the
  server's `server_now` offset.
- Autosave is per question (`PUT /attempts/{id}/answers/{qid}`), serialised client-side so responses
  never arrive out of order. Time is banked on navigation, every 30 s and when the tab is hidden.
- Correct answers are never sent to the client until the attempt is submitted.

## Scaling path

- API: stateless; add replicas behind a load balancer.
- Workers: add replicas; throughput is bound by Gemini rate limits, tune `EXTRACTION_CONCURRENCY`.
- Storage: move `app/storage.py` to object storage + CDN for figures.
- Search: the PYQ text filter uses `ILIKE`; move to Postgres full-text search or a search service when
  the bank grows past a few hundred thousand questions.
- Migrations: introduce Alembic before the first production schema change.
