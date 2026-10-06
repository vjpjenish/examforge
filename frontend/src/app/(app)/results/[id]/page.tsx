"use client";

import clsx from "clsx";
import { Award, CheckCircle2, Clock, MinusCircle, RotateCcw, Target, Trophy, XCircle } from "lucide-react";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { EditQuestionButton } from "@/components/QuestionEditor";
import { formatAnswer, QuestionView } from "@/components/QuestionView";
import { RichText } from "@/components/RichText";
import { Badge, Button, Card, ErrorNote, PageHeader, ProgressBar, Reveal, Ring, Skeleton, StatCard } from "@/components/ui";
import type { Report, ReportQuestion } from "@/lib/api";
import { formatDuration, useApi } from "@/lib/hooks";

const STATUS_COLOR: Record<ReportQuestion["status"], string> = {
  correct: "var(--success)",
  incorrect: "var(--danger)",
  unattempted: "var(--fg-subtle)",
  ungraded: "var(--warning)",
};
const tooltipStyle = { background: "var(--bg-elev)", border: "1px solid var(--border)", borderRadius: 12, fontSize: 12 };

type Filter = "all" | ReportQuestion["status"];

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const { data: r, error, setData } = useApi<Report>(`/api/attempts/${id}/report`);
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<number | null>(null);

  const timeData = useMemo(
    () => (r?.questions ?? []).map((q) => ({ name: `Q${q.order}`, seconds: q.time_seconds, status: q.status })),
    [r],
  );

  if (error) return <ErrorNote message={error} />;
  if (!r)
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-80" />
        <Skeleton className="h-56" />
        <Skeleton className="h-80" />
      </div>
    );

  const pct = r.max_score ? (100 * r.score) / r.max_score : 0;
  const avgTime = r.attempted ? r.time_seconds / Math.max(1, r.attempted + r.unattempted) : 0;
  const shown = r.questions.filter((q) => filter === "all" || q.status === filter);

  return (
    <>
      <PageHeader
        title={r.test_title}
        subtitle="Detailed performance analysis"
        actions={
          <Button variant="secondary" href={`/tests/${r.test_id}`}>
            <RotateCcw className="h-4 w-4" /> Reattempt
          </Button>
        }
      />

      <Reveal>
        <Card className="relative overflow-hidden p-6 sm:p-8">
          <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-brand/10 blur-3xl" />
          <div className="flex flex-col items-center gap-8 sm:flex-row">
            <Ring
              value={pct}
              size={160}
              label={
                <div>
                  <div className="text-3xl font-semibold tabular-nums">{r.score}</div>
                  <div className="text-xs text-subtle">of {r.max_score}</div>
                </div>
              }
            />
            <div className="grid flex-1 grid-cols-2 gap-4 sm:grid-cols-4">
              {[
                { icon: CheckCircle2, label: "Correct", value: r.correct, cls: "text-success" },
                { icon: XCircle, label: "Incorrect", value: r.incorrect, cls: "text-danger" },
                { icon: MinusCircle, label: "Unattempted", value: r.unattempted, cls: "text-subtle" },
                { icon: Target, label: "Negative marks", value: r.negative_marks, cls: "text-danger" },
              ].map(({ icon: Icon, label, value, cls }) => (
                <div key={label} className="rounded-xl bg-sunken p-4">
                  <Icon className={clsx("h-4 w-4", cls)} />
                  <div className="mt-2 text-2xl font-semibold tabular-nums">{value}</div>
                  <div className="text-xs text-subtle">{label}</div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </Reveal>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Accuracy" value={`${r.accuracy}%`} icon={<Target className="h-4 w-4" />} sub={`${r.correct} of ${r.attempted} attempted`} />
        <StatCard
          label="Time taken"
          value={formatDuration(r.time_seconds)}
          icon={<Clock className="h-4 w-4" />}
          sub={`of ${formatDuration(r.duration_seconds)} · ${formatDuration(avgTime)}/question`}
          delay={0.05}
        />
        <StatCard label="Rank" value={`#${r.rank}`} icon={<Trophy className="h-4 w-4" />} sub={`among ${r.total_attempts} attempts`} delay={0.1} />
        <StatCard label="Percentile" value={r.percentile} icon={<Award className="h-4 w-4" />} sub="higher is better" delay={0.15} />
      </div>

      <Reveal className="mt-6">
        <Card className="overflow-hidden">
          <div className="p-6 pb-2">
            <h2 className="font-semibold">Section-wise performance</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wider text-subtle">
                  {["Section", "Score", "Correct", "Incorrect", "Skipped", "Negative", "Accuracy", "Time"].map((h) => (
                    <th key={h} className="px-6 py-3 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {r.sections.map((s) => (
                  <tr key={s.name} className="border-b border-line last:border-0">
                    <td className="px-6 py-4 font-medium">{s.name}</td>
                    <td className="px-6 py-4 tabular-nums">
                      {s.score} <span className="text-subtle">/ {s.max_score}</span>
                    </td>
                    <td className="px-6 py-4 text-success tabular-nums">{s.correct}</td>
                    <td className="px-6 py-4 text-danger tabular-nums">{s.incorrect}</td>
                    <td className="px-6 py-4 text-muted tabular-nums">{s.unattempted}</td>
                    <td className="px-6 py-4 text-danger tabular-nums">{s.negative_marks}</td>
                    <td className="w-40 px-6 py-4">
                      <div className="flex items-center gap-2">
                        <ProgressBar value={s.accuracy} tone={s.accuracy >= 70 ? "success" : s.accuracy >= 40 ? "warning" : "brand"} />
                        <span className="w-10 text-right text-xs tabular-nums">{s.accuracy}%</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-muted tabular-nums">{formatDuration(s.time_seconds)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </Reveal>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Reveal className="lg:col-span-2">
          <Card className="h-full p-6">
            <h2 className="font-semibold">Time spent per question</h2>
            <p className="mb-4 text-xs text-subtle">Bars are coloured by result: spot where time was lost.</p>
            <div className="h-60">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={timeData} margin={{ left: -20, right: 4 }}>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 10, fill: "var(--fg-subtle)" }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 10, fill: "var(--fg-subtle)" }} axisLine={false} tickLine={false} unit="s" />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--bg-sunken)" }} formatter={(v) => [formatDuration(Number(v)), "Time"]} />
                  <Bar dataKey="seconds" radius={[4, 4, 0, 0]}>
                    {timeData.map((d) => (
                      <Cell key={d.name} fill={STATUS_COLOR[d.status]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </Reveal>
        <Reveal delay={0.05}>
          <Card className="h-full p-6">
            <h2 className="mb-4 font-semibold">Topic accuracy</h2>
            <div className="space-y-3">
              {r.topics.map((t) => (
                <div key={t.name}>
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="truncate pr-2 font-medium">{t.name}</span>
                    <span className="shrink-0 text-subtle">
                      {t.correct}/{t.total}
                    </span>
                  </div>
                  <ProgressBar value={t.accuracy} tone={t.accuracy >= 70 ? "success" : t.accuracy >= 40 ? "warning" : "brand"} />
                </div>
              ))}
            </div>
          </Card>
        </Reveal>
      </div>

      <Reveal className="mt-6">
        <Card className="p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-semibold">Question-wise review</h2>
            <div className="flex flex-wrap gap-1 rounded-xl bg-sunken p-1">
              {(["all", "correct", "incorrect", "unattempted"] as Filter[]).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={clsx(
                    "rounded-lg px-3 py-1.5 text-xs font-medium capitalize transition",
                    filter === f ? "bg-elev text-fg shadow-sm" : "text-muted hover:text-fg",
                  )}
                >
                  {f} {f !== "all" && `(${r.questions.filter((q) => q.status === f).length})`}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            {shown.map((q) => (
              <div key={q.question_id} className="overflow-hidden rounded-xl border border-line">
                <button
                  onClick={() => setOpen(open === q.question_id ? null : q.question_id)}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-sunken"
                >
                  <span
                    className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-xs font-semibold text-white"
                    style={{ background: STATUS_COLOR[q.status] }}
                  >
                    {q.order}
                  </span>
                  <span className="line-clamp-1 min-w-0 flex-1 text-sm text-muted">{q.text.replace(/\$|\*|\|/g, " ")}</span>
                  <Badge tone={q.marks > 0 ? "success" : q.marks < 0 ? "danger" : "neutral"}>
                    {q.marks > 0 ? "+" : ""}
                    {q.marks}
                  </Badge>
                  <span className="hidden w-16 text-right text-xs text-subtle sm:block">{formatDuration(q.time_seconds)}</span>
                </button>
                {open === q.question_id && (
                  <div className="border-t border-line bg-bg/50 p-5">
                    <QuestionView type={q.type} text={q.text} options={q.options} images={q.images} response={q.response} answer={q.answer} disabled />
                    {q.type === "numerical" && (
                      <p className="mt-2 text-sm">
                        Your answer: <span className="font-medium">{typeof q.response === "string" && q.response ? q.response : "—"}</span>
                      </p>
                    )}
                    <div className="mt-5 rounded-xl bg-brand-soft/60 p-4">
                      <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-brand">
                        Solution · Answer {formatAnswer(q.answer)}
                      </p>
                      {q.explanation ? <RichText text={q.explanation} className="text-sm" /> : <p className="text-sm text-muted">No explanation provided in the source paper.</p>}
                    </div>
                    <div className="mt-3 flex justify-end">
                      <EditQuestionButton
                        questionId={q.question_id}
                        onSaved={(saved) =>
                          setData((rep) =>
                            rep
                              ? {
                                  ...rep,
                                  questions: rep.questions.map((x) =>
                                    x.question_id === saved.id
                                      ? { ...x, text: saved.text, type: saved.type, options: saved.options, images: saved.images, answer: saved.answer, explanation: saved.explanation }
                                      : x,
                                  ),
                                }
                              : rep,
                          )
                        }
                      />
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      </Reveal>
    </>
  );
}
