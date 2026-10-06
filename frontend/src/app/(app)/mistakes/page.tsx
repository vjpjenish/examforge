"use client";

import { ArrowRight, BookMarked, CheckCircle2, ChevronDown, Clock, NotebookPen, Target, XCircle } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { QuestionView } from "@/components/QuestionView";
import { RichText } from "@/components/RichText";
import { Card, Select, Skeleton } from "@/components/ui";
import type { Mistake, MistakeBook } from "@/lib/api";
import { formatDate, formatDuration, useApi } from "@/lib/hooks";

function toLabels(value: Mistake["response"] | Mistake["answer"]): string[] {
  if (value == null) return [];
  if (Array.isArray(value)) return value as string[];
  if (typeof value === "string") return [value];
  // Numerical answers carry a value/raw rather than option labels.
  const n = value as { value?: number; raw?: string };
  return n.raw ? [n.raw] : n.value !== undefined ? [String(n.value)] : [];
}

/** Each chosen label with the option's own wording, so the box reads on its own. */
function OptionSummary({ labels, options, empty }: { labels: string[]; options: Mistake["options"]; empty: string }) {
  if (!labels.length) return <p className="mt-1 text-sm font-semibold">{empty}</p>;
  return (
    <ul className="mt-1 space-y-1">
      {labels.map((l) => {
        const text = options.find((o) => o.label === l)?.text;
        return (
          <li key={l} className="flex gap-1.5 text-sm">
            <span className="shrink-0 font-bold">{l}.</span>
            {text ? (
              <span className="min-w-0 font-medium">
                <RichText text={text} />
              </span>
            ) : (
              <span className="font-semibold">{l}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function MistakeCard({ m, index }: { m: Mistake; index: number }) {
  const [open, setOpen] = useState(false);

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line px-5 py-3">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-danger-soft text-xs font-bold text-danger">
          {index}
        </span>
        <Link href={`/results/${m.attempt_id}`} className="min-w-0 truncate text-sm font-semibold hover:text-brand">
          {m.test_title}
        </Link>
        <span className="rounded-md bg-sunken px-2 py-0.5 text-[11px] font-medium text-muted">{m.section}</span>
        {m.topic && <span className="rounded-md bg-sunken px-2 py-0.5 text-[11px] font-medium text-muted">{m.topic}</span>}
        <span className="ml-auto flex items-center gap-3 text-[11px] text-subtle">
          <span className="inline-flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {formatDuration(m.time_spent_seconds)}
          </span>
          <span>{formatDate(m.attempted_at)}</span>
          <span className="font-semibold text-danger tabular-nums">{m.marks_awarded}</span>
        </span>
      </div>

      <div className="px-5 py-4">
        <QuestionView
          type={m.type}
          text={m.text}
          options={m.options}
          images={m.images}
          response={m.response}
          answer={m.answer}
          disabled
        />

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-danger/30 bg-danger-soft px-4 py-3">
            <p className="flex items-center gap-1.5 text-[11px] font-bold tracking-wide text-danger">
              <XCircle className="h-3.5 w-3.5" /> YOU ANSWERED
            </p>
            <OptionSummary labels={toLabels(m.response)} options={m.options} empty="Not answered" />
          </div>
          <div className="rounded-xl border border-success/30 bg-success-soft px-4 py-3">
            <p className="flex items-center gap-1.5 text-[11px] font-bold tracking-wide text-success">
              <CheckCircle2 className="h-3.5 w-3.5" /> CORRECT ANSWER
            </p>
            <OptionSummary labels={toLabels(m.answer)} options={m.options} empty="Not available" />
          </div>
        </div>

        {m.explanation && (
          <div className="mt-3">
            <button
              onClick={() => setOpen((v) => !v)}
              aria-expanded={open}
              className="i-nav inline-flex items-center gap-1.5 rounded-lg text-[13px] font-semibold text-brand"
            >
              <ChevronDown className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} />
              {open ? "Hide explanation" : "Why it is wrong"}
            </button>
            {open && (
              <div className="prose-q mt-2 rounded-xl bg-sunken px-4 py-3 text-sm leading-relaxed text-muted">
                <RichText text={m.explanation} />
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

export default function MistakesPage() {
  const [testId, setTestId] = useState("");
  const [section, setSection] = useState("");
  const { data, loading } = useApi<MistakeBook>("/api/mistakes");

  const items = useMemo(() => {
    if (!data) return [];
    return data.items.filter(
      (m) => (!testId || String(m.test_id) === testId) && (!section || m.section === section),
    );
  }, [data, testId, section]);

  // Which tests contribute the most mistakes, for the summary strip.
  const worstTest = useMemo(() => {
    if (!data?.items.length) return null;
    const counts = new Map<string, number>();
    for (const m of data.items) counts.set(m.test_title, (counts.get(m.test_title) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
  }, [data]);

  if (loading && !data)
    return (
      <div className="space-y-5">
        <Skeleton className="h-12 w-72" />
        <Skeleton className="h-20" />
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-64" />
        ))}
      </div>
    );

  const all = data?.items ?? [];

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-bold tracking-[0.12em] text-subtle">REVISION</p>
          <h1 className="mt-2 text-[34px] font-bold leading-[1.1] tracking-tight sm:text-[38px]">My mistake book</h1>
          <p className="mt-2 text-[15px] text-muted">
            Every question you got wrong, gathered from all the tests you have taken.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {all.length > 0 && (
            <Link
              href={{ pathname: "/mistakes/practice", query: { ...(testId && { test_id: testId }), ...(section && { section }) } }}
              className="i-lift inline-flex h-11 items-center gap-2 rounded-xl bg-brand px-5 text-sm font-semibold text-white hover:brightness-110"
            >
              <Target className="h-4 w-4" /> Practise my mistakes
            </Link>
          )}
          <Card className="flex items-center gap-3 px-5 py-4">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-danger-soft text-danger">
            <NotebookPen className="h-[18px] w-[18px]" />
          </span>
          <div>
            <p className="text-[15px] font-bold leading-none tabular-nums">{all.length} mistakes</p>
            <p className="mt-1.5 text-xs text-subtle">
              {worstTest ? `Most from ${worstTest[0].slice(0, 28)}${worstTest[0].length > 28 ? "…" : ""}` : "Across all tests"}
            </p>
          </div>
          </Card>
        </div>
      </div>

      {all.length > 0 && (
        <Card className="mt-6 flex flex-wrap items-center gap-3 p-4">
          <span className="text-[13px] font-semibold text-muted">Filter</span>
          <div className="w-[min(100%,260px)]">
            <Select value={testId} onChange={(e) => setTestId(e.target.value)} className="h-9 text-[13px]">
              <option value="">All tests ({data?.tests.length ?? 0})</option>
              {data?.tests.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title}
                </option>
              ))}
            </Select>
          </div>
          <div className="w-[min(100%,180px)]">
            <Select value={section} onChange={(e) => setSection(e.target.value)} className="h-9 text-[13px]">
              <option value="">All sections</option>
              {data?.sections.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </div>
          <span className="ml-auto text-[13px] text-subtle tabular-nums">
            Showing {items.length} of {all.length}
          </span>
        </Card>
      )}

      {items.length ? (
        <div className="mt-5 space-y-4">
          {items.map((m, i) => (
            <MistakeCard key={m.id} m={m} index={i + 1} />
          ))}
        </div>
      ) : (
        <Card className="mt-6">
          <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
            <span className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-soft text-brand">
              <BookMarked className="h-5 w-5" />
            </span>
            <p className="mt-4 text-[15px] font-semibold">{all.length ? "Nothing matches this filter" : "No mistakes yet"}</p>
            <p className="mt-1 max-w-sm text-sm text-muted">
              {all.length
                ? "Try a different test or section."
                : "Finish a test and anything you get wrong is collected here for revision."}
            </p>
            {!all.length && (
              <Link
                href="/tests"
                className="i-lift mt-5 inline-flex h-10 items-center gap-2 rounded-xl bg-brand px-5 text-sm font-semibold text-white hover:brightness-110"
              >
                Browse tests <ArrowRight className="h-4 w-4" />
              </Link>
            )}
          </div>
        </Card>
      )}
    </>
  );
}
