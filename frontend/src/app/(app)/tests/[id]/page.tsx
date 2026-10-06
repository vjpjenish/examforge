"use client";

import { AlertCircle, CheckCircle2, Clock, Flag, ListChecks, MinusCircle, PlayCircle } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Badge, Button, Card, ErrorNote, PageHeader, Reveal, Skeleton } from "@/components/ui";
import { api, type AttemptSummary, type TestInfo } from "@/lib/api";
import { formatDate, useApi } from "@/lib/hooks";

export default function TestDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: test, error } = useApi<TestInfo>(`/api/tests/${id}`);
  const { data: attempts } = useApi<AttemptSummary[]>("/api/attempts");
  const [busy, setBusy] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  if (error) return <ErrorNote message={error} />;
  if (!test) return <Skeleton className="h-96" />;

  const past = (attempts ?? []).filter((a) => a.test_id === test.id && a.status === "submitted");

  async function start() {
    setBusy(true);
    try {
      const { attempt_id } = await api<{ attempt_id: number }>(`/api/tests/${id}/start`, { method: "POST" });
      router.push(`/attempt/${attempt_id}`);
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  const rules = [
    { icon: CheckCircle2, tone: "text-success", text: `+${test.marks_correct} for every correct answer` },
    {
      icon: MinusCircle,
      tone: "text-danger",
      text: test.marks_incorrect ? `${test.marks_incorrect} for every wrong answer` : "No negative marking",
    },
    { icon: Clock, tone: "text-brand", text: `The timer runs on the server; the test auto-submits after ${test.duration_minutes} minutes` },
    { icon: Flag, tone: "text-brand-2", text: "Mark questions for review and come back to them from the palette" },
    { icon: AlertCircle, tone: "text-warning", text: "Answers are saved automatically, so you can resume after a disconnect" },
  ];

  return (
    <>
      <PageHeader title={test.title} subtitle={test.exam?.name ?? test.description} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Reveal className="lg:col-span-2">
          <Card className="p-6">
            <h2 className="font-semibold">Instructions</h2>
            <ul className="mt-4 space-y-3">
              {rules.map(({ icon: Icon, tone, text }) => (
                <li key={text} className="flex items-start gap-3 text-sm">
                  <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} />
                  <span className="text-muted">{text}</span>
                </li>
              ))}
            </ul>
            <h3 className="mt-8 text-sm font-semibold">Sections</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              {test.sections.map((s) => (
                <Badge key={s} tone="brand">
                  {s}
                </Badge>
              ))}
            </div>
          </Card>
        </Reveal>
        <Reveal delay={0.05}>
          <Card className="p-6">
            <div className="grid grid-cols-2 gap-4 text-center">
              <div className="rounded-xl bg-sunken p-4">
                <ListChecks className="mx-auto h-5 w-5 text-brand" />
                <div className="mt-2 text-2xl font-semibold">{test.question_count}</div>
                <div className="text-xs text-subtle">Questions</div>
              </div>
              <div className="rounded-xl bg-sunken p-4">
                <Clock className="mx-auto h-5 w-5 text-brand" />
                <div className="mt-2 text-2xl font-semibold">{test.duration_minutes}</div>
                <div className="text-xs text-subtle">Minutes</div>
              </div>
            </div>
            {startError && (
              <div className="mt-4">
                <ErrorNote message={startError} />
              </div>
            )}
            <Button size="lg" className="mt-6 w-full" onClick={start} loading={busy}>
              <PlayCircle className="h-5 w-5" /> {test.in_progress_attempt_id ? "Resume test" : "Start test"}
            </Button>
            {past.length > 0 && (
              <div className="mt-6">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-subtle">Previous attempts</p>
                <ul className="space-y-2">
                  {past.map((a) => (
                    <li key={a.id}>
                      <button
                        onClick={() => router.push(`/results/${a.id}`)}
                        className="flex w-full items-center justify-between rounded-xl border border-line px-3 py-2 text-sm transition hover:bg-sunken"
                      >
                        <span className="text-muted">{formatDate(a.submitted_at)}</span>
                        <span className="font-medium tabular-nums">
                          {a.score} / {a.max_score}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>
        </Reveal>
      </div>
    </>
  );
}
