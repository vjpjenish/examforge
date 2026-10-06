"use client";

import { ArrowLeft, ArrowRight, Check, RotateCcw, Target } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

import { QuestionView, type Response } from "@/components/QuestionView";
import { RichText } from "@/components/RichText";
import { Card, ProgressBar, Skeleton } from "@/components/ui";
import type { Mistake, MistakeBook } from "@/lib/api";
import { useApi } from "@/lib/hooks";

/** Graded client-side: the mistake book already shows these answers, so nothing is hidden. */
function isRight(m: Mistake, response: Response): boolean {
  const given = Array.isArray(response) ? response : response ? [response] : [];
  if (!given.length) return false;
  const answer = m.answer;
  if (Array.isArray(answer)) {
    return answer.length === given.length && answer.every((a) => given.includes(a));
  }
  if (answer && typeof answer === "object") {
    const expected = answer.raw ?? (answer.value !== undefined ? String(answer.value) : null);
    return expected !== null && given[0]?.trim() === expected.trim();
  }
  return false;
}

function PaletteButton({
  n,
  state,
  active,
  onClick,
}: {
  n: number;
  state: "blank" | "answered" | "correct" | "wrong";
  active: boolean;
  onClick: () => void;
}) {
  const tone = {
    blank: "bg-sunken text-muted",
    answered: "bg-brand text-white",
    correct: "bg-success text-white",
    wrong: "bg-danger text-white",
  }[state];
  return (
    <button
      onClick={onClick}
      className={`grid h-9 w-9 place-items-center rounded-lg text-xs font-bold transition ${tone} ${
        active ? "ring-2 ring-brand ring-offset-2 ring-offset-[var(--bg-elev)]" : ""
      }`}
    >
      {n}
    </button>
  );
}

function PracticeRunner({ items }: { items: Mistake[] }) {
  const [current, setCurrent] = useState(0);
  const [responses, setResponses] = useState<Record<number, Response>>({});
  const [submitted, setSubmitted] = useState(false);

  const answeredCount = Object.values(responses).filter(
    (r) => r != null && (Array.isArray(r) ? r.length > 0 : true),
  ).length;
  const score = useMemo(
    () => items.filter((m) => isRight(m, responses[m.id] ?? null)).length,
    [items, responses],
  );

  const m = items[current];

  if (submitted) {
    const pct = items.length ? Math.round((100 * score) / items.length) : 0;
    const fixed = items.filter((x) => isRight(x, responses[x.id] ?? null));
    const stillWrong = items.filter((x) => !isRight(x, responses[x.id] ?? null));

    return (
      <>
        <Card className="p-6">
          <div className="flex flex-wrap items-center justify-between gap-5">
            <div>
              <p className="text-[11px] font-bold tracking-[0.12em] text-subtle">PRACTICE COMPLETE</p>
              <h2 className="mt-2 text-[30px] font-bold leading-none tracking-tight">
                {score} <span className="text-muted">/ {items.length} fixed</span>
              </h2>
              <p className="mt-2 text-sm text-muted">
                {pct >= 80
                  ? "Strong recovery — these are sticking now."
                  : pct >= 50
                    ? "Good progress. Run the ones you missed again."
                    : "Worth another pass — review the explanations below."}
              </p>
            </div>
            <div className="w-full max-w-xs">
              <div className="mb-2 flex justify-between text-xs font-medium">
                <span className="text-success">{fixed.length} right</span>
                <span className="text-danger">{stillWrong.length} still wrong</span>
              </div>
              <ProgressBar value={pct} tone={pct >= 50 ? "success" : "warning"} />
            </div>
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            <button
              onClick={() => {
                setResponses({});
                setCurrent(0);
                setSubmitted(false);
              }}
              className="i-lift inline-flex h-10 items-center gap-2 rounded-xl bg-brand px-5 text-sm font-semibold text-white hover:brightness-110"
            >
              <RotateCcw className="h-4 w-4" /> Practise again
            </button>
            <Link
              href="/mistakes"
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-line px-5 text-sm font-semibold text-muted transition hover:text-fg"
            >
              <ArrowLeft className="h-4 w-4" /> Back to mistake book
            </Link>
          </div>
        </Card>

        <div className="mt-5 space-y-4">
          {items.map((x, i) => {
            const right = isRight(x, responses[x.id] ?? null);
            return (
              <Card key={x.id} className="overflow-hidden">
                <div className="flex items-center gap-3 border-b border-line px-5 py-3">
                  <span
                    className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg text-xs font-bold ${
                      right ? "bg-success-soft text-success" : "bg-danger-soft text-danger"
                    }`}
                  >
                    {i + 1}
                  </span>
                  <span className={`text-sm font-semibold ${right ? "text-success" : "text-danger"}`}>
                    {right ? "Correct this time" : "Still wrong"}
                  </span>
                  <span className="ml-auto truncate text-xs text-subtle">{x.test_title}</span>
                </div>
                <div className="px-5 py-4">
                  <QuestionView
                    type={x.type}
                    text={x.text}
                    options={x.options}
                    images={x.images}
                    response={responses[x.id] ?? null}
                    answer={x.answer}
                    disabled
                  />
                  {x.explanation && (
                    <div className="prose-q mt-4 rounded-xl bg-sunken px-4 py-3 text-sm leading-relaxed text-muted">
                      <RichText text={x.explanation} />
                    </div>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      </>
    );
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_260px]">
      <Card className="flex min-w-0 flex-col p-6">
        <div className="mb-4 flex items-center justify-between gap-3">
          <span className="rounded-lg bg-brand px-2.5 py-1 text-xs font-bold text-white">Q {current + 1}</span>
          <span className="truncate text-xs text-subtle">{m.test_title}</span>
        </div>

        <QuestionView
          type={m.type}
          text={m.text}
          options={m.options}
          images={m.images}
          response={responses[m.id] ?? null}
          onChange={(r) => setResponses((s) => ({ ...s, [m.id]: r }))}
        />

        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
          <button
            onClick={() => setResponses((s) => ({ ...s, [m.id]: null }))}
            className="inline-flex h-9 items-center gap-1.5 rounded-xl px-3 text-sm font-medium text-muted transition hover:text-fg"
          >
            Clear
          </button>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrent((c) => Math.max(0, c - 1))}
              disabled={current === 0}
              className="inline-flex h-10 items-center gap-1.5 rounded-xl border border-line px-4 text-sm font-medium text-muted transition hover:text-fg disabled:opacity-40"
            >
              <ArrowLeft className="h-4 w-4" /> Prev
            </button>
            {current < items.length - 1 ? (
              <button
                onClick={() => setCurrent((c) => c + 1)}
                className="i-lift inline-flex h-10 items-center gap-2 rounded-xl bg-brand px-5 text-sm font-semibold text-white hover:brightness-110"
              >
                Next <ArrowRight className="h-4 w-4" />
              </button>
            ) : (
              <button
                onClick={() => setSubmitted(true)}
                className="i-lift inline-flex h-10 items-center gap-2 rounded-xl bg-success px-5 text-sm font-semibold text-white hover:brightness-110"
              >
                <Check className="h-4 w-4" /> Finish practice
              </button>
            )}
          </div>
        </div>
      </Card>

      <Card className="h-fit p-5">
        <p className="text-[13px] font-bold">Progress</p>
        <p className="mt-1 text-xs text-muted">
          {answeredCount} of {items.length} answered
        </p>
        <div className="mt-3">
          <ProgressBar value={items.length ? (100 * answeredCount) / items.length : 0} />
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          {items.map((x, i) => {
            const r = responses[x.id];
            const has = r != null && (Array.isArray(r) ? r.length > 0 : true);
            return (
              <PaletteButton
                key={x.id}
                n={i + 1}
                state={has ? "answered" : "blank"}
                active={i === current}
                onClick={() => setCurrent(i)}
              />
            );
          })}
        </div>
        <button
          onClick={() => setSubmitted(true)}
          className="i-lift mt-6 flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-success text-sm font-bold text-white hover:brightness-110"
        >
          <Check className="h-4 w-4" /> Finish practice
        </button>
      </Card>
    </div>
  );
}

function PracticeBody() {
  const params = useSearchParams();
  const testId = params.get("test_id") ?? "";
  const section = params.get("section") ?? "";
  const { data, loading } = useApi<MistakeBook>("/api/mistakes");

  const items = useMemo(() => {
    if (!data) return [];
    return data.items.filter(
      (m) => (!testId || String(m.test_id) === testId) && (!section || m.section === section),
    );
  }, [data, testId, section]);

  if (loading && !data)
    return (
      <div className="space-y-5">
        <Skeleton className="h-12 w-72" />
        <Skeleton className="h-[420px]" />
      </div>
    );

  return (
    <>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-bold tracking-[0.12em] text-subtle">REVISION</p>
          <h1 className="mt-2 text-[32px] font-bold leading-[1.1] tracking-tight">Practise my mistakes</h1>
          <p className="mt-2 text-[15px] text-muted">
            {items.length
              ? `Answer all ${items.length} again — scored at the end.`
              : "Nothing to practise yet."}
          </p>
        </div>
        <Link
          href="/mistakes"
          className="inline-flex h-10 items-center gap-2 rounded-xl border border-line px-4 text-sm font-medium text-muted transition hover:text-fg"
        >
          <ArrowLeft className="h-4 w-4" /> Mistake book
        </Link>
      </div>

      {items.length ? (
        <PracticeRunner key={`${testId}|${section}|${items.length}`} items={items} />
      ) : (
        <Card>
          <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
            <span className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-soft text-brand">
              <Target className="h-5 w-5" />
            </span>
            <p className="mt-4 text-[15px] font-semibold">No mistakes to practise</p>
            <p className="mt-1 max-w-sm text-sm text-muted">
              Finish a test first — anything you get wrong lands in your mistake book, ready to practise here.
            </p>
            <Link
              href="/tests"
              className="i-lift mt-5 inline-flex h-10 items-center gap-2 rounded-xl bg-brand px-5 text-sm font-semibold text-white hover:brightness-110"
            >
              Browse tests <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </Card>
      )}
    </>
  );
}

export default function PracticePage() {
  // useSearchParams needs a Suspense boundary during prerender.
  return (
    <Suspense fallback={<Skeleton className="h-[420px]" />}>
      <PracticeBody />
    </Suspense>
  );
}
