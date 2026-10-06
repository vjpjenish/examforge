"use client";

import clsx from "clsx";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Eraser,
  FileText,
  Loader2,
  Plus,
  Search,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

import { Button, Card, EmptyState, ErrorNote, Field, Input, ProgressBar, Select, Skeleton } from "@/components/ui";
import { api, type DocumentInfo, type Exam } from "@/lib/api";
import { formatDate, useApi } from "@/lib/hooks";

const KINDS = [
  { value: "test_series", label: "Test series", hint: "A question paper that becomes a timed, scored test." },
  { value: "pyq", label: "PYQ paper", hint: "A previous-year paper that joins the PYQ library." },
  { value: "solutions", label: "Solutions", hint: "An answer key or explanations for a paper you already uploaded." },
] as const;

const KIND_LABEL: Record<string, string> = { test_series: "Test series", pyq: "PYQ", solutions: "Solutions" };

/** Questions a document has produced. `flagged` is a marker on other buckets, not a bucket. */
function questionTotal(doc: DocumentInfo) {
  return Object.entries(doc.question_counts)
    .filter(([k]) => k !== "flagged")
    .reduce((a, [, v]) => a + v, 0);
}

/* ------------------------------------------------------------------ cleared ids */

/**
 * Clearing hides a document from this list only — it is never deleted. Deleting
 * would cascade into the document's questions, any test built from them and
 * students' PYQ progress, so this keeps to the list. Cleared ids are remembered
 * per browser; anything uploaded later is not in the set, so new uploads still
 * appear here on their own.
 */
const CLEARED_KEY = "examforge.clearedDocuments";

// A tiny external store, so the value is read during render rather than set from
// an effect, and the server snapshot ("nothing cleared") stays hydration-safe.
let clearedListeners: (() => void)[] = [];
function subscribeCleared(onChange: () => void) {
  clearedListeners.push(onChange);
  return () => {
    clearedListeners = clearedListeners.filter((l) => l !== onChange);
  };
}

const EMPTY = "[]";
let cachedRaw = EMPTY;
let cachedIds: number[] = [];

/** Returns a stable array reference, which useSyncExternalStore requires. */
function readClearedIds(): number[] {
  let raw = EMPTY;
  try {
    raw = localStorage.getItem(CLEARED_KEY) ?? EMPTY;
  } catch {
    /* storage unavailable (private mode) */
  }
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    try {
      const parsed: unknown = JSON.parse(raw);
      cachedIds = Array.isArray(parsed) ? parsed.filter((n): n is number => typeof n === "number") : [];
    } catch {
      cachedIds = [];
    }
  }
  return cachedIds;
}

function writeClearedIds(ids: number[]) {
  try {
    localStorage.setItem(CLEARED_KEY, JSON.stringify([...new Set(ids)]));
  } catch {
    /* storage unavailable — the list still clears for this session */
  }
  clearedListeners.forEach((l) => l());
}

const SERVER_IDS: number[] = [];

/* ------------------------------------------------------------------- status */

function StatusPill({ doc }: { doc: DocumentInfo }) {
  const job = doc.latest_job;
  const base = "inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold";
  if (!job) return <span className={clsx(base, "bg-sunken text-muted")}>No job</span>;
  if (job.status === "completed")
    return (
      <span className={clsx(base, "bg-success-soft text-success")}>
        <CheckCircle2 className="h-3 w-3" /> Extracted
      </span>
    );
  if (job.status === "failed")
    return (
      <span className={clsx(base, "bg-danger-soft text-danger")}>
        <AlertTriangle className="h-3 w-3" /> Failed
      </span>
    );
  return (
    <span className={clsx(base, "bg-brand-soft text-brand")}>
      <Loader2 className="h-3 w-3 animate-spin" />
      {job.status === "queued" ? "Queued" : `${job.stage} ${Math.round(job.progress * 100)}%`}
    </span>
  );
}

/* ------------------------------------------------------------------- upload */

function UploadDialog({
  exams,
  papers,
  onClose,
  onDone,
  onExamCreated,
}: {
  exams: Exam[];
  papers: DocumentInfo[];
  onClose: () => void;
  onDone: () => void;
  onExamCreated: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [form, setForm] = useState({
    title: "",
    kind: "test_series",
    exam_id: "",
    institution: "",
    year: "",
    solutions_for: "",
    marks_correct: "",
    marks_incorrect: "",
    duration_minutes: "",
  });
  const [newExam, setNewExam] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const isSolutions = form.kind === "solutions";
  const isTestSeries = form.kind === "test_series";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const pick = (f: File | undefined) => {
    if (!f) return;
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
      setError("Please choose a PDF file");
      return;
    }
    setError(null);
    setFile(f);
    if (!form.title) setForm((s) => ({ ...s, title: f.name.replace(/\.pdf$/i, "").replace(/[_-]+/g, " ") }));
  };

  async function addExam() {
    if (!newExam.trim()) return;
    try {
      const exam = await api<Exam>("/api/exams", { method: "POST", json: { name: newExam.trim() } });
      setForm((s) => ({ ...s, exam_id: String(exam.id) }));
      setNewExam("");
      onExamCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return setError("Choose a PDF first");
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.append("file", file);
    Object.entries(form).forEach(([k, v]) => {
      // A solutions PDF inherits exam and year from its paper; a paper has no "solutions for";
      // and a marking scheme only applies to a test series.
      if (!v) return;
      if (isSolutions && ["exam_id", "year", "institution"].includes(k)) return;
      if (!isSolutions && k === "solutions_for") return;
      if (!isTestSeries && ["marks_correct", "marks_incorrect", "duration_minutes"].includes(k)) return;
      body.append(k, v);
    });
    try {
      await api("/api/documents", { method: "POST", body });
      onDone();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return createPortal(
    <>
      <motion.div
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={() => !busy && onClose()}
      />
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label="Upload a paper"
        className="fixed inset-0 z-50 grid place-items-center overflow-y-auto p-4"
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 12, scale: 0.98 }}
        transition={{ duration: 0.2 }}
      >
        <form
          onSubmit={submit}
          onClick={(e) => e.stopPropagation()}
          className="my-auto w-full max-w-3xl overflow-hidden rounded-2xl border border-line bg-elev shadow-2xl"
        >
          <div className="flex items-start gap-3 border-b border-line px-6 py-5">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand">
              <UploadCloud className="h-5 w-5" />
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="text-[17px] font-bold tracking-tight">Upload a paper</h2>
              <p className="mt-0.5 text-sm text-muted">
                Any layout works — questions are extracted and published for you.
              </p>
            </div>
            <span className="hidden shrink-0 items-center gap-1.5 rounded-full bg-brand-soft px-3 py-1.5 text-xs font-semibold text-brand sm:inline-flex">
              <Sparkles className="h-3.5 w-3.5" /> AI powered
            </span>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-subtle transition hover:bg-sunken hover:text-fg"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="grid max-h-[min(70vh,640px)] gap-6 overflow-y-auto p-6 md:grid-cols-[minmax(0,260px)_minmax(0,1fr)]">
            <div className="min-w-0 space-y-4">
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDrag(true);
                }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDrag(false);
                  pick(e.dataTransfer.files[0]);
                }}
                onClick={() => inputRef.current?.click()}
                className={clsx(
                  "i-drop flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-4 py-10 text-center",
                  drag ? "border-brand bg-brand-soft" : "border-line",
                )}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept="application/pdf,.pdf"
                  className="hidden"
                  onChange={(e) => {
                    pick(e.target.files?.[0]);
                    e.target.value = ""; // allow choosing the same file again
                  }}
                />
                <AnimatePresence mode="wait">
                  {file ? (
                    <motion.div key="file" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}>
                      <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-brand-soft text-brand">
                        <FileText className="h-5 w-5" />
                      </span>
                      <p className="mt-3 max-w-[200px] truncate text-sm font-semibold">{file.name}</p>
                      <p className="mt-0.5 text-xs text-subtle">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setFile(null);
                        }}
                        className="mt-2 inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-subtle transition hover:text-danger"
                      >
                        <X className="h-3 w-3" /> Remove
                      </button>
                    </motion.div>
                  ) : (
                    <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                      <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-brand-soft text-brand">
                        <UploadCloud className="h-5 w-5" />
                      </span>
                      <p className="mt-3 text-[15px] font-semibold">Drop a PDF here</p>
                      <p className="mt-1 text-xs text-subtle">or click to browse</p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              <div>
                <span className="mb-2 block text-sm font-medium text-fg">Type</span>
                <div className="space-y-1.5">
                  {KINDS.map((k) => (
                    <button
                      key={k.value}
                      type="button"
                      onClick={() => setForm({ ...form, kind: k.value })}
                      className={clsx(
                        "i-nav flex w-full items-center gap-2 rounded-xl border px-3 py-2.5 text-left text-sm",
                        form.kind === k.value
                          ? "border-brand bg-brand-soft font-semibold text-brand"
                          : "border-line font-medium text-muted hover:text-fg",
                      )}
                    >
                      <span
                        className={clsx(
                          "grid h-4 w-4 shrink-0 place-items-center rounded-full border-2",
                          form.kind === k.value ? "border-brand" : "border-line",
                        )}
                      >
                        {form.kind === k.value && <span className="h-1.5 w-1.5 rounded-full bg-brand" />}
                      </span>
                      {k.label}
                    </button>
                  ))}
                </div>
                <p className="mt-2 text-xs text-subtle">{KINDS.find((k) => k.value === form.kind)?.hint}</p>
              </div>
            </div>

            <div className="min-w-0 space-y-4">
              <Field label="Title">
                <Input
                  required
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder="JEE Main Mock Test 12"
                />
              </Field>

              {isSolutions ? (
                <Field
                  label="Solutions for"
                  hint={
                    papers.length
                      ? "Live papers only: published tests and the PYQ bank. Answers attach to their questions."
                      : "Nothing to attach to yet — upload a test series or PYQ paper first."
                  }
                >
                  <Select
                    value={form.solutions_for}
                    onChange={(e) => setForm({ ...form, solutions_for: e.target.value })}
                  >
                    <option value="">Match by title automatically</option>
                    {papers.map((p) => (
                      <option key={p.id} value={p.id}>
                        #{p.id} · {KIND_LABEL[p.kind]} · {p.title} — {questionTotal(p)} questions
                        {p.year ? `, ${p.year}` : ""}
                      </option>
                    ))}
                  </Select>
                </Field>
              ) : (
                <>
                  <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_120px]">
                    <Field label="Exam" hint="Groups PYQs into their own workspace">
                      <Select value={form.exam_id} onChange={(e) => setForm({ ...form, exam_id: e.target.value })}>
                        <option value="">Select exam</option>
                        {exams.map((x) => (
                          <option key={x.id} value={x.id}>
                            {x.name}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <Field label="Year">
                      <Input
                        type="number"
                        min={1950}
                        max={2100}
                        value={form.year}
                        onChange={(e) => setForm({ ...form, year: e.target.value })}
                        placeholder="Auto"
                      />
                    </Field>
                  </div>
                  <div className="flex gap-2">
                    <Input
                      value={newExam}
                      onChange={(e) => setNewExam(e.target.value)}
                      placeholder="Add new exam (e.g. NEET UG)"
                    />
                    <Button type="button" variant="secondary" onClick={addExam} aria-label="Add exam">
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                  <Field label="Institution">
                    <Input
                      value={form.institution}
                      onChange={(e) => setForm({ ...form, institution: e.target.value })}
                      placeholder="Optional"
                    />
                  </Field>
                </>
              )}

              {isTestSeries && (
                <div className="rounded-2xl border border-line p-4">
                  <p className="text-sm font-semibold">Marking scheme</p>
                  <p className="mt-1 text-xs text-subtle">
                    Used when this paper is published as a test. Leave blank to use whatever the paper states.
                  </p>
                  <div className="mt-3 grid gap-3 sm:grid-cols-3">
                    <Field label="Marks">
                      <Input
                        type="number"
                        step="0.25"
                        min={0}
                        max={100}
                        value={form.marks_correct}
                        onChange={(e) => setForm({ ...form, marks_correct: e.target.value })}
                        placeholder="4"
                      />
                    </Field>
                    <Field label="Penalty">
                      <Input
                        type="number"
                        step="0.25"
                        min={0}
                        max={100}
                        value={form.marks_incorrect}
                        onChange={(e) => setForm({ ...form, marks_incorrect: e.target.value })}
                        placeholder="1"
                      />
                    </Field>
                    <Field label="Minutes">
                      <Input
                        type="number"
                        min={1}
                        max={1440}
                        value={form.duration_minutes}
                        onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })}
                        placeholder="60"
                      />
                    </Field>
                  </div>
                  <p className="mt-2 text-[11px] text-subtle">
                    Enter the penalty as a positive number — it is applied as a deduction.
                  </p>
                </div>
              )}

              {error && <ErrorNote message={error} />}
            </div>
          </div>

          <div className="flex items-center justify-end gap-3 border-t border-line bg-sunken/40 px-6 py-4">
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-10 items-center rounded-xl px-4 text-sm font-medium text-muted transition hover:text-fg"
            >
              Cancel
            </button>
            <Button type="submit" loading={busy} disabled={!file}>
              <UploadCloud className="h-4 w-4" /> Upload &amp; extract
            </Button>
          </div>
        </form>
      </motion.div>
    </>,
    document.body,
  );
}

/* --------------------------------------------------------------------- rows */

function DocumentRow({
  doc,
  paperTitle,
  onClear,
}: {
  doc: DocumentInfo;
  paperTitle: (id: number | null) => string | undefined;
  onClear: () => void;
}) {
  const job = doc.latest_job;
  const total = questionTotal(doc);
  const running = job != null && ["queued", "running"].includes(job.status);
  const meta = [doc.exam?.name, doc.institution?.name, doc.year, `${doc.page_count} pages`, formatDate(doc.created_at)]
    .filter(Boolean)
    .join(" · ");

  return (
    <li className="i-row group relative flex items-center gap-4 border-b border-line px-5 py-4 last:border-0">
      <span
        className={clsx(
          "grid h-11 w-11 shrink-0 place-items-center rounded-xl",
          doc.kind === "pyq"
            ? "bg-warning-soft text-warning"
            : doc.kind === "solutions"
              ? "bg-info/10 text-info"
              : "bg-brand-soft text-brand",
        )}
      >
        <FileText className="h-[18px] w-[18px]" />
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Link href={`/admin/documents/${doc.id}`} className="min-w-0 truncate font-semibold hover:text-brand">
            {doc.title}
          </Link>
          <span className="shrink-0 rounded-md bg-sunken px-2 py-0.5 text-[11px] font-medium text-muted">
            {KIND_LABEL[doc.kind]}
          </span>
        </div>
        <p className="mt-1 truncate text-xs text-subtle">{meta}</p>

        {running && (
          <div className="mt-3 max-w-sm">
            <ProgressBar value={job.progress * 100} />
          </div>
        )}

        {job?.status === "completed" && doc.kind === "solutions" && (
          <p className="mt-2 text-xs text-muted">
            {doc.answer_key_entries ?? 0} answers &amp; explanations ·{" "}
            {paperTitle(doc.solutions_for_id) ? <>for {paperTitle(doc.solutions_for_id)}</> : "no paper linked"}
          </p>
        )}

        {job?.status === "completed" && doc.kind !== "solutions" && (
          <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
            <span>{total} questions</span>
            <span className="text-success">{doc.question_counts.approved ?? 0} published</span>
            <span className="text-warning">{doc.question_counts.flagged ?? 0} to check</span>
            {doc.solutions.length > 0 && <span>{doc.solutions.length} solutions PDF</span>}
          </p>
        )}

        {doc.kind === "test_series" && (doc.marks_correct != null || doc.duration_minutes != null) && (
          <p className="mt-1.5 flex flex-wrap gap-x-3 text-[11px] text-subtle">
            {doc.marks_correct != null && <span>+{doc.marks_correct} per question</span>}
            {doc.marks_incorrect != null && <span>{doc.marks_incorrect} wrong</span>}
            {doc.duration_minutes != null && <span>{doc.duration_minutes} min</span>}
          </p>
        )}

        {job?.status === "failed" && <p className="mt-2 line-clamp-1 text-xs text-danger">{job.error}</p>}
      </div>

      <StatusPill doc={doc} />

      <div className="flex shrink-0 items-center gap-1">
        <Link
          href={`/admin/documents/${doc.id}`}
          aria-label={`Review ${doc.title}`}
          className="grid h-8 w-8 place-items-center rounded-lg text-subtle transition hover:bg-sunken hover:text-fg"
        >
          <ChevronRight className="h-4 w-4" />
        </Link>
        <button
          onClick={onClear}
          title="Clear from this list"
          aria-label={`Clear ${doc.title} from this list`}
          className="grid h-8 w-8 place-items-center rounded-lg text-subtle opacity-60 transition hover:bg-danger-soft hover:text-danger hover:opacity-100 focus-visible:opacity-100"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </li>
  );
}

/* --------------------------------------------------------------------- page */

export default function AdminPage() {
  const { data: docs, loading, reload } = useApi<DocumentInfo[]>("/api/documents");
  const { data: exams, reload: reloadExams } = useApi<Exam[]>("/api/exams");
  const clearedIds = useSyncExternalStore(subscribeCleared, readClearedIds, () => SERVER_IDS);
  const cleared = new Set(clearedIds);

  const [uploading, setUploading] = useState(false);
  const [kind, setKind] = useState("");
  const [search, setSearch] = useState("");

  const clearOne = (id: number) => writeClearedIds([...clearedIds, id]);

  const all = useMemo(() => docs ?? [], [docs]);
  const visibleDocs = useMemo(() => all.filter((d) => !cleared.has(d.id)), [all, clearedIds]); // eslint-disable-line react-hooks/exhaustive-deps
  const hiddenCount = all.length - visibleDocs.length;

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    return visibleDocs.filter(
      (d) => (!kind || d.kind === kind) && (!q || d.title.toLowerCase().includes(q)),
    );
  }, [visibleDocs, kind, search]);

  const clearList = () => writeClearedIds([...clearedIds, ...shown.map((d) => d.id)]);

  /**
   * Papers an answer key can be attached to.
   *
   * A test series counts once it is live as a test — the same list "My tests" shows. Extracting a
   * paper is not enough: its test can be deleted afterwards, leaving a document nobody can reach.
   * A PYQ paper never becomes a test, so there it is having questions in the bank that makes it live.
   */
  const solutionTargets = useMemo(
    () =>
      all.filter((d) => {
        if (d.kind === "solutions") return false;
        if (d.kind === "test_series") return d.test_id != null;
        return questionTotal(d) > 0;
      }),
    [all],
  );

  const active = all.some((d) => d.latest_job && ["queued", "running"].includes(d.latest_job.status));
  const paperTitle = (id: number | null) => all.find((d) => d.id === id)?.title;
  useEffect(() => {
    if (!active) return;
    const t = setInterval(reload, 2500);
    return () => clearInterval(t);
  }, [active, reload]);

  const tabs = [
    { value: "", label: "All", count: visibleDocs.length },
    ...KINDS.map((k) => ({
      value: k.value,
      label: KIND_LABEL[k.value],
      count: visibleDocs.filter((d) => d.kind === k.value).length,
    })),
  ];

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-bold tracking-[0.12em] text-subtle">LIBRARY</p>
          <h1 className="mt-2 text-[34px] font-bold leading-[1.1] tracking-tight sm:text-[38px]">PDF extraction</h1>
          <p className="mt-2 text-[15px] text-muted">
            Upload papers and their solutions. Extracted questions are published to tests and the PYQ bank
            automatically.
          </p>
        </div>
        <button
          onClick={() => setUploading(true)}
          className="i-lift inline-flex h-11 shrink-0 items-center gap-2 rounded-xl bg-brand px-5 text-sm font-semibold text-white hover:brightness-110"
        >
          <Plus className="h-4 w-4" /> Upload paper
        </button>
      </div>

      <Card className="mt-7 overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-4">
          <div className="flex flex-wrap gap-1 rounded-xl bg-sunken p-1">
            {tabs.map((t) => (
              <button
                key={t.value}
                onClick={() => setKind(t.value)}
                className={clsx(
                  "rounded-lg px-3 py-1.5 text-[13px] transition",
                  kind === t.value ? "bg-elev font-semibold shadow-sm" : "font-medium text-muted hover:text-fg",
                )}
              >
                {t.label}
                <span className="ml-1.5 text-[11px] text-subtle tabular-nums">{t.count}</span>
              </button>
            ))}
          </div>

          <div className="relative ml-auto w-full sm:w-56">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Find a document"
              aria-label="Find a document"
              className="h-9 w-full rounded-xl border border-line bg-elev pl-9 pr-3 text-sm outline-none transition-all duration-200 placeholder:text-subtle focus:border-brand focus:ring-4 focus:ring-brand/12"
            />
          </div>

          {!!shown.length && (
            <button
              onClick={clearList}
              className="i-lift inline-flex h-9 shrink-0 items-center gap-1.5 rounded-xl border border-line px-3 text-xs font-medium text-muted hover:text-fg"
            >
              <Eraser className="h-3.5 w-3.5" /> Clear
            </button>
          )}
        </div>

        {loading && !docs ? (
          <div className="space-y-3 p-5">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
        ) : shown.length ? (
          <ul>
            {shown.map((d) => (
              <DocumentRow key={d.id} doc={d} paperTitle={paperTitle} onClear={() => clearOne(d.id)} />
            ))}
          </ul>
        ) : (
          <div className="p-5">
            {visibleDocs.length ? (
              <EmptyState
                icon={<Search className="h-5 w-5" />}
                title="Nothing matches"
                body="Try another type, or a different search."
              />
            ) : hiddenCount > 0 ? (
              <EmptyState
                icon={<Eraser className="h-5 w-5" />}
                title="List cleared"
                body={`${hiddenCount} document${hiddenCount === 1 ? "" : "s"} cleared from this list. Nothing was deleted — new uploads appear here.`}
              />
            ) : (
              <EmptyState
                icon={<UploadCloud className="h-5 w-5" />}
                title="No documents yet"
                body="Upload your first test series or PYQ PDF."
                action={
                  <Button onClick={() => setUploading(true)}>
                    <Plus className="h-4 w-4" /> Upload paper
                  </Button>
                }
              />
            )}
          </div>
        )}
      </Card>

      <AnimatePresence>
        {uploading && (
          <UploadDialog
            exams={exams ?? []}
            papers={solutionTargets}
            onClose={() => setUploading(false)}
            onDone={reload}
            onExamCreated={reloadExams}
          />
        )}
      </AnimatePresence>
    </>
  );
}
