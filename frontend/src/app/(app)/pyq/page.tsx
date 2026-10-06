"use client";

import clsx from "clsx";
import { ArrowRight, Bookmark, BookOpenCheck, CheckCircle2, ChevronLeft, ChevronRight, Library, Search, Trash2, XCircle } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { EditQuestionButton } from "@/components/QuestionEditor";
import { formatAnswer, QuestionView, type Response } from "@/components/QuestionView";
import { RichText } from "@/components/RichText";
import { Badge, Button, Card, EmptyState, ErrorNote, Input, PageHeader, ProgressBar, Reveal, Select, Skeleton } from "@/components/ui";
import { api, type PyqItem, type PyqStats } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";

const STATUSES = [
  ["", "All"],
  ["unsolved", "Unsolved"],
  ["solved", "Solved"],
  ["incorrect", "Got wrong"],
  ["bookmarked", "Bookmarked"],
] as const;

function PyqCard({
  item,
  onChange,
  onRemoved,
  onError,
}: {
  item: PyqItem;
  onChange: (i: PyqItem) => void;
  onRemoved: () => void;
  onError: (message: string) => void;
}) {
  const { user } = useAuth();
  const [response, setResponse] = useState<Response>(item.progress?.last_response ?? null);
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState(false);
  const solved = !!item.progress?.solved;
  const [reveal, setReveal] = useState(solved);

  async function check() {
    if (!response || (Array.isArray(response) && !response.length)) return;
    setBusy(true);
    try {
      onChange(await api<PyqItem>(`/api/pyq/${item.id}/answer`, { method: "POST", json: { response } }));
      setReveal(true);
    } finally {
      setBusy(false);
    }
  }

  async function bookmark() {
    const { bookmarked } = await api<{ bookmarked: boolean }>(`/api/pyq/${item.id}/bookmark`, { method: "POST" });
    onChange({ ...item, progress: { ...(item.progress ?? { solved: false, is_correct: null, attempts: 0, last_response: null }), bookmarked } });
  }

  async function remove() {
    if (!confirm("Remove this question from the PYQ bank? It stays on the uploaded paper and can be restored from the admin review page.")) return;
    setRemoving(true);
    try {
      await api(`/api/pyq/${item.id}`, { method: "DELETE" });
      onRemoved();
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
      setRemoving(false);
    }
  }

  const result = item.progress?.is_correct;
  return (
    <Card className="p-5 sm:p-6">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {item.year && <Badge tone="brand">{item.year}</Badge>}
        <Badge>{item.subject ?? item.section}</Badge>
        {item.topic && <Badge>{item.topic}</Badge>}
        {solved && (
          <Badge tone={result ? "success" : result === false ? "danger" : "neutral"}>
            {result ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
            {result ? "Solved" : result === false ? "Incorrect" : "Attempted"}
          </Badge>
        )}
        <button
          onClick={bookmark}
          aria-label="Bookmark"
          className={clsx("ml-auto grid h-8 w-8 place-items-center rounded-lg transition hover:bg-sunken", item.progress?.bookmarked ? "text-warning" : "text-subtle")}
        >
          <Bookmark className="h-4 w-4" fill={item.progress?.bookmarked ? "currentColor" : "none"} />
        </button>
        {user?.role === "admin" && (
          <button
            onClick={remove}
            disabled={removing}
            aria-label="Remove from PYQ bank"
            title="Remove from PYQ bank"
            className="grid h-8 w-8 place-items-center rounded-lg text-subtle transition hover:bg-sunken hover:text-danger disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
      <QuestionView
        type={item.type}
        text={item.text}
        options={item.options}
        images={item.images}
        response={response}
        onChange={(r) => {
          setResponse(r);
          setReveal(false);
        }}
        answer={reveal ? item.answer : undefined}
      />
      <div className="mt-5 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={check} loading={busy} disabled={!response || (Array.isArray(response) && !response.length)}>
          Check answer
        </Button>
        {solved && !reveal && (
          <Button size="sm" variant="ghost" onClick={() => setReveal(true)}>
            Show solution
          </Button>
        )}
        <span className="ml-auto">
          <EditQuestionButton
            questionId={item.id}
            onSaved={(q) =>
              onChange({ ...item, text: q.text, type: q.type, options: q.options, images: q.images, answer: q.answer, explanation: q.explanation })
            }
          />
        </span>
      </div>
      {reveal && item.answer !== null && (
        <div className="mt-4 rounded-xl bg-brand-soft/60 p-4">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-brand">Answer {formatAnswer(item.answer)}</p>
          {item.explanation ? <RichText text={item.explanation} className="text-sm" /> : <p className="text-sm text-muted">No explanation in the source paper.</p>}
        </div>
      )}
    </Card>
  );
}

function PyqLibrary({
  scope,
  initialSearch,
  onBack,
}: {
  scope: Scope;
  initialSearch: string;
  onBack: () => void;
}) {
  const [filters, setFilters] = useState({ subject: "", year: "", status: "", q: initialSearch });
  const [search, setSearch] = useState(initialSearch);
  const [page, setPage] = useState(1);
  const scopeQs = scopeParams(scope);
  const { data: meta } = useApi<{ subjects: string[]; years: number[] }>(`/api/pyq/filters?${scopeQs}`);
  const { data: stats, reload: reloadStats } = useApi<PyqStats>(`/api/pyq/stats?${scopeQs}`);

  const qs = new URLSearchParams(scopeQs);
  qs.set("page", String(page));
  qs.set("page_size", "10");
  Object.entries(filters).forEach(([k, v]) => v && qs.set(k, v));
  const { data, loading, setData, reload } = useApi<{ total: number; items: PyqItem[] }>(`/api/pyq?${qs}`);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setFilters((f) => ({ ...f, q: search }));
      setPage(1);
    }, 350);
    return () => clearTimeout(t);
  }, [search]);

  const set = (k: keyof typeof filters) => (v: string) => {
    setFilters((f) => ({ ...f, [k]: v }));
    setPage(1);
  };
  const pages = data ? Math.max(1, Math.ceil(data.total / 10)) : 1;

  return (
    <>
      <button
        onClick={onBack}
        className="i-nav mb-4 inline-flex items-center gap-1.5 rounded-lg text-[13px] font-semibold text-brand"
      >
        <ChevronLeft className="h-4 w-4" /> All workspaces
      </button>
      <PageHeader
        title={scope.name}
        subtitle={
          scope.kind === "all"
            ? "Previous-year questions from every workspace."
            : "Previous-year questions in this workspace."
        }
      />
      {failed && <ErrorNote message={failed} />}

      {stats && (
        <Reveal>
          <Card className="mb-6 grid gap-6 p-6 sm:grid-cols-[220px_1fr]">
            <div>
              <p className="text-sm text-muted">Overall progress</p>
              <p className="mt-1 text-3xl font-semibold tabular-nums">
                {stats.solved}
                <span className="text-lg text-subtle"> / {stats.total}</span>
              </p>
              <p className="mt-1 text-xs text-subtle">{stats.accuracy}% accuracy on solved</p>
              <div className="mt-3">
                <ProgressBar value={stats.total ? (100 * stats.solved) / stats.total : 0} tone="success" />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {stats.by_subject.map((s) => (
                <button key={s.subject} onClick={() => set("subject")(filters.subject === s.subject ? "" : s.subject)} className="text-left">
                  <div className="mb-1 flex justify-between text-xs">
                    <span className={clsx("font-medium", filters.subject === s.subject && "text-brand")}>{s.subject}</span>
                    <span className="text-subtle">
                      {s.solved}/{s.total}
                    </span>
                  </div>
                  <ProgressBar value={s.total ? (100 * s.solved) / s.total : 0} />
                </button>
              ))}
            </div>
          </Card>
        </Reveal>
      )}

      <div className="mb-6 flex flex-col gap-3 lg:flex-row">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search question text" className="pl-9" />
        </div>
        <Select value={filters.subject} onChange={(e) => set("subject")(e.target.value)} className="lg:w-48">
          <option value="">All subjects</option>
          {meta?.subjects.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </Select>
        <Select value={filters.year} onChange={(e) => set("year")(e.target.value)} className="lg:w-32">
          <option value="">All years</option>
          {meta?.years.map((y) => (
            <option key={y}>{y}</option>
          ))}
        </Select>
      </div>
      <div className="mb-6 flex flex-wrap gap-1 rounded-xl bg-sunken p-1 sm:inline-flex">
        {STATUSES.map(([value, label]) => (
          <button
            key={value}
            onClick={() => set("status")(value)}
            className={clsx(
              "rounded-lg px-3 py-1.5 text-xs font-medium transition",
              filters.status === value ? "bg-elev text-fg shadow-sm" : "text-muted hover:text-fg",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && !data ? (
        <div className="space-y-4">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      ) : data?.items.length ? (
        <div className="space-y-4">
          {data.items.map((item, i) => (
            <Reveal key={item.id} delay={Math.min(i, 4) * 0.04}>
              <PyqCard
                item={item}
                onError={setFailed}
                onChange={(next) => {
                  setData((d) => (d ? { ...d, items: d.items.map((x) => (x.id === next.id ? next : x)) } : d));
                  void reloadStats();
                }}
                onRemoved={() => {
                  setFailed(null);
                  // Refetch rather than only splicing: the page is server-paginated, so dropping a row
                  // locally would leave a short page (and an empty one on the last page).
                  if (data && data.items.length === 1 && page > 1) setPage(page - 1);
                  else reload();
                  void reloadStats();
                }}
              />
            </Reveal>
          ))}
          <div className="flex items-center justify-between pt-2">
            <p className="text-sm text-muted">
              Page {page} of {pages} · {data.total} questions
            </p>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <EmptyState icon={<BookOpenCheck className="h-5 w-5" />} title="No questions match" body="Try a different filter, or ask an admin to upload PYQ papers." />
      )}
    </>
  );
}

type Scope =
  | { kind: "all"; name: string }
  | { kind: "unassigned"; name: string }
  | { kind: "exam"; id: number; name: string };

interface Workspace {
  exam_id: number | null;
  name: string;
  unassigned: boolean;
  total: number;
  solved: number;
  correct: number;
  accuracy: number;
  year_from: number | null;
  year_to: number | null;
  subjects: number;
}

/** Query string that pins every bank request to the open workspace. */
function scopeParams(scope: Scope) {
  if (scope.kind === "unassigned") return "unassigned=true";
  if (scope.kind === "exam") return `exam_id=${scope.id}`;
  return "";
}

function WorkspacePicker({ onOpen }: { onOpen: (value: string) => void }) {
  const { data, loading } = useApi<Workspace[]>("/api/pyq/workspaces");

  if (loading && !data)
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-44" />
        ))}
      </div>
    );

  const spaces = data ?? [];
  const grandTotal = spaces.reduce((a, w) => a + w.total, 0);

  return (
    <>
      <PageHeader
        title="PYQ library"
        subtitle="Each workspace is an exam. Open one to practise only its previous-year questions."
      />

      {spaces.length ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {spaces.map((w) => {
              const pct = w.total ? (100 * w.solved) / w.total : 0;
              const years =
                w.year_from && w.year_to
                  ? w.year_from === w.year_to
                    ? String(w.year_from)
                    : `${w.year_from} to ${w.year_to}`
                  : null;
              return (
                <button
                  key={w.exam_id ?? "unassigned"}
                  onClick={() => onOpen(w.unassigned ? "unsorted" : String(w.exam_id))}
                  className="i-lift group text-left"
                >
                  <Card className="flex h-full flex-col p-5">
                    <div className="flex items-start gap-3">
                      <span
                        className={clsx(
                          "grid h-11 w-11 shrink-0 place-items-center rounded-xl",
                          w.unassigned ? "bg-sunken text-muted" : "bg-brand-soft text-brand",
                        )}
                      >
                        <Library className="h-5 w-5" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[17px] font-bold tracking-tight">{w.name}</p>
                        <p className="mt-0.5 text-xs text-muted">
                          {[years, `${w.subjects} subject${w.subjects === 1 ? "" : "s"}`].filter(Boolean).join(" \u00b7 ")}
                        </p>
                      </div>
                      <ArrowRight className="h-4 w-4 shrink-0 text-subtle transition-transform group-hover:translate-x-0.5" />
                    </div>

                    <div className="mt-5">
                      <div className="mb-1.5 flex items-baseline justify-between">
                        <span className="text-[22px] font-bold leading-none tabular-nums">
                          {w.solved}
                          <span className="text-sm font-medium text-subtle"> / {w.total}</span>
                        </span>
                        <span className="text-xs text-subtle">{Math.round(pct)}% solved</span>
                      </div>
                      <ProgressBar value={pct} tone="success" />
                    </div>

                    {w.unassigned && (
                      <p className="mt-4 text-[11px] leading-snug text-subtle">
                        Papers uploaded without an exam. Pick an exam when uploading to file them into their own
                        workspace.
                      </p>
                    )}
                  </Card>
                </button>
              );
            })}
          </div>

          {spaces.length > 1 && (
            <button
              onClick={() => onOpen("all")}
              className="i-nav mt-5 inline-flex items-center gap-1.5 rounded-lg text-[13px] font-semibold text-brand"
            >
              Browse all {grandTotal} questions across workspaces <ArrowRight className="h-3.5 w-3.5" />
            </button>
          )}
        </>
      ) : (
        <EmptyState
          icon={<Library className="h-5 w-5" />}
          title="No PYQ workspaces yet"
          body="Upload a previous-year paper and pick its exam, and it becomes a workspace here."
        />
      )}
    </>
  );
}

function PyqBody() {
  const router = useRouter();
  const params = useSearchParams();
  const exam = params.get("exam");
  const search = params.get("q") ?? "";
  const { data: spaces } = useApi<Workspace[]>("/api/pyq/workspaces");

  const open = (value: string) => router.push(`/pyq?exam=${value}`);
  const back = () => router.push("/pyq");

  // A global search with no workspace chosen looks across all of them.
  if (!exam && !search) return <WorkspacePicker onOpen={open} />;

  let scope: Scope;
  if (!exam || exam === "all") scope = { kind: "all", name: "All PYQs" };
  else if (exam === "unsorted") scope = { kind: "unassigned", name: "Unsorted" };
  else {
    const id = Number(exam);
    const match = spaces?.find((w) => w.exam_id === id);
    scope = { kind: "exam", id, name: match?.name ?? "Workspace" };
  }

  return <PyqLibrary key={exam ?? "search"} scope={scope} initialSearch={search} onBack={back} />;
}

export default function PyqPage() {
  // useSearchParams needs a Suspense boundary during prerender.
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <PyqBody />
    </Suspense>
  );
}
