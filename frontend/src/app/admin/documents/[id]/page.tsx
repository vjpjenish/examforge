"use client";

import clsx from "clsx";
import { AlertTriangle, BookOpenCheck, Check, ExternalLink, FileImage, FileText, Pencil, RefreshCw, RotateCcw, ShieldCheck, Sparkles, Trash2, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { QuestionEditor } from "@/components/QuestionEditor";
import { formatAnswer, QuestionView } from "@/components/QuestionView";
import { RichText } from "@/components/RichText";
import { Badge, Button, Card, EmptyState, ErrorNote, PageHeader, ProgressBar, Reveal, Skeleton } from "@/components/ui";
import { api, API_URL, getToken, type DocumentInfo, type Question } from "@/lib/api";
import { useApi } from "@/lib/hooks";

type Filter = "check" | "approved" | "rejected" | "all";
const FLAG_THRESHOLD = 0.8;
const isFlagged = (q: Question) => q.issues.length > 0 || q.confidence < FLAG_THRESHOLD;
const FILTER_LABEL: Record<Filter, string> = { check: "To check", approved: "Published", rejected: "Rejected", all: "All" };

type Stats = Record<string, unknown>;
const list = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : []);
const num = (v: unknown) => (typeof v === "number" ? v : 0);

function PageViewer({ docId, page, onClose }: { docId: number; page: number; onClose: () => void }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let url = "";
    fetch(`${API_URL}/api/documents/${docId}/pages/${page}.png`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.blob())
      .then((b) => {
        url = URL.createObjectURL(b);
        setSrc(url);
      });
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [docId, page]);
  return (
    <motion.div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
      <motion.div initial={{ scale: 0.96 }} animate={{ scale: 1 }} className="relative max-h-full overflow-auto rounded-2xl bg-white p-2 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} aria-label="Close" className="absolute right-3 top-3 rounded-full bg-black/60 p-1.5 text-white">
          <X className="h-4 w-4" />
        </button>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {src ? <img src={src} alt={`Page ${page}`} className="max-h-[85vh] w-auto" /> : <div className="skeleton h-[70vh] w-[50vh]" />}
      </motion.div>
    </motion.div>
  );
}

function sourceLabel(source: string | null) {
  if (!source) return null;
  if (source.startsWith("solutions:")) return "from solutions PDF";
  return { inline: "printed with question", answer_key: "from answer key", edited: "edited by a person" }[source] ?? source;
}

function QuestionCard({ q, onChange, onPage }: { q: Question; onChange: (q: Question) => void; onPage: (p: number) => void }) {
  const [editing, setEditing] = useState(false);
  const setStatus = async (review_status: Question["review_status"]) =>
    onChange(await api<Question>(`/api/questions/${q.id}`, { method: "PATCH", json: { review_status } }));
  const flagged = isFlagged(q);

  return (
    <Card className={clsx("p-5 sm:p-6", flagged && q.review_status === "approved" && "border-warning/50", q.review_status === "rejected" && "opacity-70")}>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="rounded-lg bg-sunken px-2 py-0.5 text-xs font-semibold">Q{q.number || q.order_index + 1}</span>
        <Badge>{q.section}</Badge>
        {q.topic && <Badge>{q.topic}</Badge>}
        <Badge tone={q.confidence >= 0.9 ? "success" : q.confidence >= FLAG_THRESHOLD ? "warning" : "danger"}>
          <Sparkles className="h-3 w-3" /> {Math.round(q.confidence * 100)}%
        </Badge>
        {q.review_status === "rejected" ? <Badge tone="danger">rejected</Badge> : <Badge tone="success">published</Badge>}
        {q.edit_count > 0 && (
          <Badge tone="brand">
            <Pencil className="h-3 w-3" /> edited
          </Badge>
        )}
        <div className="ml-auto flex gap-1">
          {q.source_pages.map((p) => (
            <button key={p} onClick={() => onPage(p)} className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-muted transition hover:bg-sunken hover:text-fg">
              <FileImage className="h-3.5 w-3.5" /> p.{p}
            </button>
          ))}
        </div>
      </div>

      {q.issues.length > 0 && !editing && (
        <div className="mb-4 rounded-xl border border-warning/30 bg-warning-soft px-4 py-3">
          {q.issues.map((i) => (
            <p key={i} className="flex items-start gap-2 text-xs text-warning">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {i}
            </p>
          ))}
        </div>
      )}

      {editing ? (
        <QuestionEditor
          q={q}
          onCancel={() => setEditing(false)}
          onSaved={(s) => {
            onChange(s);
            setEditing(false);
          }}
        />
      ) : (
        <>
          <QuestionView type={q.type} text={q.text} options={q.options} images={q.images} response={null} answer={q.answer} disabled />
          <div className="mt-4 rounded-xl bg-sunken px-4 py-3 text-sm">
            <span className="font-medium">Answer:</span> {q.answer === null ? <span className="text-muted">unknown (not printed in the PDF)</span> : formatAnswer(q.answer)}
            {sourceLabel(q.answer_source) && <span className="ml-2 text-xs text-subtle">{sourceLabel(q.answer_source)}</span>}
            {q.explanation && <RichText text={q.explanation} className="mt-2 text-muted" />}
          </div>
          <div className="mt-4 flex flex-wrap justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
              <Pencil className="h-4 w-4" /> Edit
            </Button>
            {q.review_status === "rejected" ? (
              <Button size="sm" variant="secondary" onClick={() => setStatus("approved")}>
                <RotateCcw className="h-4 w-4" /> Restore
              </Button>
            ) : (
              <Button size="sm" variant="secondary" onClick={() => setStatus("rejected")}>
                <X className="h-4 w-4" /> Reject
              </Button>
            )}
          </div>
        </>
      )}
    </Card>
  );
}

function Notes({ stats }: { stats: Stats }) {
  const notes: { tone: "warning" | "danger" | "muted"; text: string }[] = [];
  const missing = list(stats.missing_numbers);
  if (missing.length) notes.push({ tone: "warning", text: `Question numbers not found: ${missing.slice(0, 20).join(", ")}${missing.length > 20 ? "…" : ""}` });
  const recovered = list(stats.recovered_numbers);
  if (recovered.length) notes.push({ tone: "muted", text: `Recovered by re-reading pages: ${recovered.join(", ")}` });
  const unprocessed = list(stats.unprocessed_pages);
  if (unprocessed.length) notes.push({ tone: "danger", text: `Pages not processed (re-extract to retry, finished pages are reused): ${unprocessed.join(", ")}` });
  const incomplete = list(stats.incomplete_text_pages);
  if (incomplete.length) notes.push({ tone: "muted", text: `Read from the page image (text layer missing or broken): pages ${incomplete.slice(0, 20).join(", ")}` });
  for (const c of list(stats.conflicts).slice(0, 5)) notes.push({ tone: "warning", text: c });
  if (stats.profile_error) notes.push({ tone: "muted", text: "Format detection fell back to the text layer." });
  if (stats.quota_exhausted || stats.verify_skipped === "quota") notes.push({ tone: "warning", text: "The Gemini daily quota ran out during this run." });
  if (!notes.length) return null;
  return (
    <div className="col-span-full space-y-1">
      {notes.map((n) => (
        <p key={n.text} className={clsx("text-xs", n.tone === "danger" ? "text-danger" : n.tone === "warning" ? "text-warning" : "text-muted")}>
          <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />
          {n.text}
        </p>
      ))}
    </div>
  );
}

function StatGrid({ items }: { items: [string, unknown][] }) {
  return (
    <>
      {items.map(([label, value]) => (
        <div key={label}>
          <p className="text-xs text-subtle">{label}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{String(value ?? 0)}</p>
        </div>
      ))}
    </>
  );
}

export default function DocumentPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: doc, reload: reloadDoc, error } = useApi<DocumentInfo>(`/api/documents/${id}`);
  const { data: questions, setData, reload: reloadQs } = useApi<Question[]>(`/api/documents/${id}/questions`);
  const [filter, setFilter] = useState<Filter>("check");
  const [page, setPage] = useState<number | null>(null);

  const job = doc?.latest_job;
  const running = !!job && ["queued", "running"].includes(job.status);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(reloadDoc, 2000);
    return () => clearInterval(t);
  }, [running, reloadDoc]);
  useEffect(() => {
    if (job?.status === "completed") void reloadQs();
  }, [job?.status, job?.id, reloadQs]);

  const counts = useMemo(() => {
    const qs = questions ?? [];
    return {
      all: qs.length,
      check: qs.filter((q) => isFlagged(q) && q.review_status !== "rejected").length,
      approved: qs.filter((q) => q.review_status === "approved").length,
      rejected: qs.filter((q) => q.review_status === "rejected").length,
    };
  }, [questions]);

  if (error) return <ErrorNote message={error} />;
  if (!doc) return <Skeleton className="h-96" />;

  const effectiveFilter: Filter = filter === "check" && !counts.check ? "all" : filter;
  const shown = (questions ?? []).filter((q) =>
    effectiveFilter === "all" ? true : effectiveFilter === "check" ? isFlagged(q) && q.review_status !== "rejected" : q.review_status === effectiveFilter,
  );
  const stats = (job?.stats ?? {}) as Stats;
  const profile = (doc.profile ?? {}) as Record<string, unknown>;
  const isSolutions = doc.kind === "solutions";
  const stages = isSolutions ? ["loading", "parsing", "reading pages", "applying"] : ["loading", "profiling", "extracting", "recovering", "verifying", "saving"];

  async function reextract() {
    if (!confirm("Run extraction again? Questions people have edited are kept; pages already read are reused.")) return;
    await api(`/api/documents/${id}/reextract`, { method: "POST" });
    void reloadDoc();
  }
  async function remove() {
    if (!confirm(isSolutions ? "Delete this solutions PDF? Answers already applied to the paper stay." : "Delete this document, its questions and its test?")) return;
    await api(`/api/documents/${id}`, { method: "DELETE" });
    router.push("/admin");
  }

  return (
    <>
      <PageHeader
        title={doc.title}
        subtitle={[doc.exam?.name, doc.institution?.name, doc.year, `${doc.page_count} pages`].filter(Boolean).join(" · ")}
        actions={
          <>
            <Button variant="ghost" onClick={remove} aria-label="Delete document">
              <Trash2 className="h-4 w-4" />
            </Button>
            <Button variant="secondary" onClick={reextract} disabled={running}>
              <RefreshCw className="h-4 w-4" /> Re-extract
            </Button>
            {doc.test_id && (
              <Link href={`/tests/${doc.test_id}`}>
                <Button>
                  <ExternalLink className="h-4 w-4" /> Open test
                </Button>
              </Link>
            )}
            {doc.kind === "pyq" && job?.status === "completed" && (
              <Link href="/pyq">
                <Button>
                  <BookOpenCheck className="h-4 w-4" /> PYQ bank
                </Button>
              </Link>
            )}
            {isSolutions && doc.solutions_for_id && (
              <Link href={`/admin/documents/${doc.solutions_for_id}`}>
                <Button>
                  <FileText className="h-4 w-4" /> Question paper
                </Button>
              </Link>
            )}
          </>
        }
      />

      {running && job && (
        <Reveal>
          <Card className="mb-6 p-6">
            <div className="mb-3 flex items-center justify-between text-sm">
              <span className="font-medium capitalize">{job.status === "queued" ? "Waiting for a worker…" : `${job.stage}…`}</span>
              <span className="tabular-nums text-muted">{Math.round(job.progress * 100)}%</span>
            </div>
            <ProgressBar value={job.progress * 100} />
            <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-xs text-subtle">
              {stages.map((s) => (
                <span key={s} className={clsx("capitalize", job.stage === s && "font-semibold text-brand")}>
                  {s}
                </span>
              ))}
            </div>
          </Card>
        </Reveal>
      )}
      {job?.status === "failed" && (
        <div className="mb-6">
          <ErrorNote message={`Extraction failed: ${job.error}`} />
        </div>
      )}

      {job?.status === "completed" && (
        <div className="mb-6 grid gap-4 lg:grid-cols-3">
          <Reveal className="lg:col-span-2">
            <Card className="grid h-full grid-cols-2 gap-4 p-6 sm:grid-cols-4">
              {isSolutions ? (
                <StatGrid
                  items={[
                    ["Entries", stats.entries],
                    ["From text", stats.from_text],
                    ["From page images", stats.from_vision],
                    ["Applied to paper", (stats.applied as Stats | undefined)?.matched ?? 0],
                  ]}
                />
              ) : (
                <StatGrid
                  items={[
                    ["Questions", stats.questions],
                    ["With answers", stats.with_answers],
                    ["With explanations", stats.with_explanations],
                    ["To check", stats.flagged],
                  ]}
                />
              )}
              {isSolutions && list(stats.missing).length > 0 && (
                <p className="col-span-full text-xs text-warning">
                  <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />
                  No answer or explanation found for: {list(stats.missing).slice(0, 25).join(", ")}
                </p>
              )}
              <Notes stats={stats} />
            </Card>
          </Reveal>
          <Reveal delay={0.05}>
            <Card className="h-full p-6 text-sm">
              <p className="mb-2 flex items-center gap-2 font-semibold">
                <ShieldCheck className="h-4 w-4 text-brand" /> {isSolutions ? "Source" : "Detected format"}
              </p>
              <dl className="space-y-1 text-xs">
                {[
                  ["Layout", profile.layout],
                  ["Answers", profile.answer_location],
                  ["Questions", profile.total_questions],
                  ["Languages", Array.isArray(profile.languages) ? (profile.languages as string[]).join(", ") : ""],
                  ["Sections", Array.isArray(profile.sections) ? (profile.sections as { name: string }[]).map((s) => s.name).join(", ") : ""],
                  ["Engine", `${stats.provider ?? ""} · ${num(stats.gemini_calls)} AI calls · ${stats.seconds ?? "?"}s`],
                ]
                  .filter(([, v]) => v)
                  .map(([k, v]) => (
                    <div key={k as string} className="flex gap-2">
                      <dt className="w-20 shrink-0 text-subtle">{k as string}</dt>
                      <dd className="text-muted">{String(v)}</dd>
                    </div>
                  ))}
              </dl>
              {!isSolutions && (
                <div className="mt-4 border-t border-line pt-3 text-xs">
                  <p className="mb-1 font-medium">Solutions</p>
                  {doc.solutions.length ? (
                    doc.solutions.map((s) => (
                      <Link key={s.id} href={`/admin/documents/${s.id}`} className="block text-brand hover:underline">
                        {s.title} {s.status && s.status !== "completed" && <span className="text-subtle">({s.status})</span>}
                      </Link>
                    ))
                  ) : (
                    <p className="text-subtle">None linked. Upload the answer key or solutions PDF with type &ldquo;Solutions&rdquo;.</p>
                  )}
                </div>
              )}
            </Card>
          </Reveal>
        </div>
      )}

      {!isSolutions && questions && questions.length > 0 && (
        <>
          <div className="sticky top-14 z-20 -mx-4 mb-4 flex flex-wrap items-center gap-2 bg-bg/85 px-4 py-3 backdrop-blur-xl lg:top-0">
            <div className="flex flex-wrap gap-1 rounded-xl bg-sunken p-1">
              {(["check", "approved", "rejected", "all"] as Filter[]).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={clsx(
                    "rounded-lg px-3 py-1.5 text-xs font-medium transition",
                    effectiveFilter === f ? "bg-elev text-fg shadow-sm" : "text-muted hover:text-fg",
                  )}
                >
                  {FILTER_LABEL[f]} ({counts[f]})
                </button>
              ))}
            </div>
            <p className="ml-auto text-xs text-subtle">Everything is live. Fix or reject anything that looks wrong.</p>
          </div>
          <div className="space-y-4">
            {shown.map((q) => (
              <QuestionCard
                key={q.id}
                q={q}
                onPage={setPage}
                onChange={(next) => setData((qs) => (qs ? qs.map((x) => (x.id === next.id ? next : x)) : qs))}
              />
            ))}
            {!shown.length && <EmptyState icon={<Check className="h-5 w-5" />} title="Nothing here" />}
          </div>
        </>
      )}

      <AnimatePresence>{page !== null && <PageViewer docId={doc.id} page={page} onClose={() => setPage(null)} />}</AnimatePresence>
    </>
  );
}
