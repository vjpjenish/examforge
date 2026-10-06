# ExamForge: AI exam preparation platform

Upload Test Series and Previous Year Question (PYQ) PDFs from any institute. An AI extraction engine
(Google Gemini) turns them into structured questions: text, options, sections, answers, explanations and
figures. Students then practise with timed online tests, a PYQ bank and detailed analytics.

```
frontend/   Next.js 16 · React 19 · Tailwind 4 · Motion · Recharts · KaTeX   (port 3000)
backend/    FastAPI · SQLAlchemy 2 · PostgreSQL · PyMuPDF · google-genai       (port 8000)
            └─ app/extraction/   the PDF → question engine
```

## Features

| Area | What you get |
| --- | --- |
| **AI extraction** | Template-free: works on single/two-column, bilingual, scanned, and answer-key-at-the-end papers. Extracts sections, MCQ (single/multi), numerical and subjective questions, LaTeX math, tables, and cropped figures. |
| **Accuracy safeguards** | Layout profiling, overlapping page windows, page-straddling question stitching, duplicate merging, answer-key joining, a structural validator, and a stronger-model re-verification pass for anything doubtful. |
| **Admin review** | Flagged-first queue, validator issues per question, confidence score, source page viewer, inline editor with live LaTeX preview, bulk approve, re-extract. |
| **Online tests** | Server-authoritative timer, auto-submit, resume after disconnect, sections, question palette, mark for review, autosave, positive/negative/unattempted marking (per-question overrides supported). |
| **Analysis** | Score, accuracy, correct/incorrect/unattempted, negative marks, section-wise table, time per question, topic accuracy, rank & percentile, question-by-question solutions. |
| **PYQ bank** | Filter by subject/year/status/text, check answers instantly, solved/unsolved/incorrect/bookmarked tracking, per-subject progress. |
| **Dashboard** | Score & accuracy trend, section accuracy, weak areas, PYQ progress, recent tests. |
| **UI** | Responsive, light/dark themes, Lenis smooth scrolling, subtle Motion animations, reduced-motion support. |

## Quick start (local)

Requirements: Python 3.11+, Node 20+, PostgreSQL 14+ (or Docker).

```bash
# 1. Database
docker run -d --name exam-db -e POSTGRES_USER=exam -e POSTGRES_PASSWORD=exam -e POSTGRES_DB=exam -p 5432:5432 postgres:16-alpine

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # put your GEMINI_API_KEY in .env
uvicorn app.main:app --reload   # EMBEDDED_WORKER=true runs extraction in-process

# 3. Frontend
cd ../frontend
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000 and sign in as the bootstrap admin (`ADMIN_EMAIL` / `ADMIN_PASSWORD`,
default `admin@example.com` / `admin12345`, **change these**). Go to *PDF extraction*, upload a paper,
review the extracted questions, then *Publish test* (test series) or approve them into the PYQ bank.

No Gemini key yet? Set `EXTRACTION_PROVIDER=heuristic` to use the offline regex extractor (only for
clean, conventional layouts), and try `python scripts/make_sample_pdf.py sample.pdf` for a demo paper.

### Docker Compose

```bash
cp backend/.env.example backend/.env   # add GEMINI_API_KEY
docker compose up --build              # db + api + 2 extraction workers + web
```

## How the extraction engine works

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design. In short:

1. **Slice**: PyMuPDF cuts the PDF into one-page PDFs (vectors and fonts intact, annotations dropped).
   The native text layer is read too, but only for the printed-answer-key parser and offline mode.
2. **Profile**: Gemini looks at the first pages plus samples and describes the *format*: sections and
   their question ranges, numbering/option style, columns, where answers live, marking scheme.
3. **Extract**: pages are sent in small windows (default 2 pages + 1 lookahead page) in parallel, each
   page as a native one-page PDF, so Gemini runs its own layout pass over the real page instead of a
   raster. No text layer is sent: a column-interleaved one misleads the model about which options
   belong to which stem. Each call must return JSON matching a strict schema
   (`app/extraction/schemas.py`).
4. **Merge**: windows are stitched: continuation fragments are joined, duplicates from overlapping
   windows merged, sections carried forward, answer keys joined to questions (including keys whose
   numbering restarts per section).
5. **Validate**: every question is checked: option count/sequence, answer ∈ options, missing answers,
   figure references without a figure, unbalanced LaTeX, numbering gaps (missed questions).
6. **Verify**: flagged or low-confidence questions are re-read by a stronger model
   (`GEMINI_VERIFY_MODEL`) against their source pages.
7. **Save**: figures are cropped at high DPI from model bounding boxes; questions land in the review
   queue with confidence and issues.

## Testing

```bash
cd backend && pytest                       # SQLite
TEST_DATABASE_URL=postgresql+psycopg://exam:exam@localhost:5432/exam_test pytest   # Postgres (wipes it)
cd frontend && npx tsc --noEmit && npm run lint && npm run build
```

The backend suite covers the merge/validation logic, the pipeline with a fake model (windows, lookahead,
verification, partial failure), and the full HTTP flow: upload → extract → review → publish → attempt →
grading/analytics → PYQ bank → dashboard → permissions.

## Deploying

Frontend on Vercel, backend on Render: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). The API cannot run
on Vercel — it needs a long-lived process and a persistent disk for PDFs and figures.

## Production notes

- Run extraction workers separately: `python -m app.worker`. They claim jobs with
  `SELECT … FOR UPDATE SKIP LOCKED`, so you can run as many as you like against one Postgres.
- Storage is local disk (`app/storage.py`); swap in S3/GCS before running multiple API hosts.
- Tables are created with `create_all` on startup; add Alembic migrations before the first schema change
  in production.
- Set a strong `JWT_SECRET`, real admin credentials and `CORS_ORIGINS`.
- Gemini model names are configurable; pick the newest Flash/Pro models available to your key.
