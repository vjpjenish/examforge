"use client";

import { ArrowRight, BookOpen, Clock, FileText, Flame, Play, Target, TrendingUp } from "lucide-react";
import Link from "next/link";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ExamCountdown } from "@/components/ExamCountdown";
import { Card, Skeleton } from "@/components/ui";
import type { Dashboard } from "@/lib/api";
import { formatDate, useApi } from "@/lib/hooks";

const tooltipStyle = {
  background: "var(--bg-elev)",
  border: "1px solid var(--border)",
  borderRadius: 12,
  fontSize: 12,
  color: "var(--fg)",
};

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

function today() {
  return new Date()
    .toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })
    .toUpperCase();
}

function hhmmss(total: number) {
  const s = Math.max(0, Math.round(total));
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

function sinceLabel(iso: string) {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "Started just now";
  if (mins < 60) return `Started ${mins} min${mins === 1 ? "" : "s"} ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `Started ${h} hour${h === 1 ? "" : "s"} ago`;
  const d = Math.round(h / 24);
  return `Started ${d} day${d === 1 ? "" : "s"} ago`;
}

/* ------------------------------------------------------------ practice activity */

const WEEKS = 18;

/** Monday-first grid of the last `WEEKS` weeks, newest column on the right. */
function buildWeeks(days: Dashboard["activity"]["days"]) {
  const byDate = new Map(days.map((d) => [d.date, d]));
  const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

  const end = new Date();
  end.setHours(0, 0, 0, 0);
  // Walk forward to the Sunday that closes the current week.
  end.setDate(end.getDate() + ((7 - end.getDay()) % 7));

  const cells: { date: Date; key: string; tests: number; minutes: number; future: boolean }[] = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  for (let i = WEEKS * 7 - 1; i >= 0; i--) {
    const d = new Date(end);
    d.setDate(end.getDate() - i);
    const hit = byDate.get(iso(d));
    cells.push({
      date: d,
      key: iso(d),
      tests: hit?.tests ?? 0,
      minutes: hit?.minutes ?? 0,
      future: d > today,
    });
  }
  const weeks: (typeof cells)[] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  return weeks;
}

const LEVELS = ["bg-fg/[0.08]", "bg-brand/25", "bg-brand/45", "bg-brand/70", "bg-brand"];
const level = (tests: number) => (tests === 0 ? 0 : tests >= 4 ? 4 : tests);

function PracticeActivity({ data }: { data: Dashboard }) {
  const weeks = buildWeeks(data.activity.days);
  const activeDays = data.activity.days.filter((d) => d.tests > 0).length;
  const totalMinutes = data.activity.days.reduce((a, d) => a + d.minutes, 0);

  // A month label sits above the first column that begins a new month.
  const monthLabel = (w: (typeof weeks)[number], i: number) => {
    const first = w[0].date;
    if (i === 0) return first.toLocaleDateString(undefined, { month: "short" });
    const prev = weeks[i - 1][0].date;
    return first.getMonth() !== prev.getMonth() ? first.toLocaleDateString(undefined, { month: "short" }) : "";
  };

  return (
    <Card className="flex h-full flex-col p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-[17px] font-bold tracking-tight">Practice activity</h2>
          <p className="mt-1 text-sm text-muted">Every day you sat down for a test, over the last 18 weeks.</p>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-brand-soft px-3 py-1.5 text-xs font-semibold text-brand">
          <Flame className="h-3.5 w-3.5" /> {data.streak.current}-day streak
        </span>
      </div>

      <div className="mt-6 flex min-w-0 flex-1 flex-col justify-center">
        <div className="flex gap-2">
          <div className="flex shrink-0 flex-col text-[10px] leading-none text-subtle">
            <div className="h-4" aria-hidden />
            <div className="flex flex-1 flex-col gap-[3px]">
              {["Mon", "", "Wed", "", "Fri", "", ""].map((label, i) => (
                <div key={i} className="flex flex-1 items-center">
                  {label}
                </div>
              ))}
            </div>
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex gap-[3px]">
              {weeks.map((w, i) => (
                <div key={w[0].key} className="min-w-0 flex-1 text-[10px] leading-none text-subtle">
                  {monthLabel(w, i)}
                </div>
              ))}
            </div>
            <div className="mt-1.5 flex gap-[3px]">
              {weeks.map((w) => (
                <div key={w[0].key} className="flex min-w-0 flex-1 flex-col gap-[3px]">
                  {w.map((c) => (
                    <div
                      key={c.key}
                      title={
                        c.future
                          ? ""
                          : `${c.date.toLocaleDateString(undefined, { day: "numeric", month: "short" })} — ${
                              c.tests ? `${c.tests} test${c.tests === 1 ? "" : "s"}, ${c.minutes} min` : "no practice"
                            }`
                      }
                      className={`aspect-square w-full rounded-[3px] ${c.future ? "bg-transparent" : LEVELS[level(c.tests)]}`}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-3 flex items-center justify-end gap-1.5 text-[10px] text-subtle">
          <span>Less</span>
          {LEVELS.map((c) => (
            <span key={c} className={`h-2.5 w-2.5 rounded-[3px] ${c}`} />
          ))}
          <span>More</span>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-3 gap-3 border-t border-line pt-4">
        {[
          ["Active days", activeDays],
          ["Time practised", `${Math.round(totalMinutes / 6) / 10}h`],
          ["Best streak", `${data.streak.best}d`],
        ].map(([label, value]) => (
          <div key={label as string}>
            <p className="text-[11px] text-muted">{label}</p>
            <p className="mt-1 text-[19px] font-bold leading-none tabular-nums">{value}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------- continue card */

function ContinueCard({ data }: { data: Dashboard }) {
  const c = data.continue_test;

  if (!c) {
    return (
      <div className="flex h-full flex-col justify-between rounded-2xl bg-gradient-to-br from-[#4b3bc4] via-[#3a2b9e] to-[#241a63] p-6 text-white">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-white/60">Start learning</p>
          <h3 className="mt-3 text-[22px] font-bold leading-tight">No test in progress</h3>
          <p className="mt-1.5 text-sm text-white/70">
            Pick a paper and your progress will be saved as you go.
          </p>
        </div>
        <Link
          href="/tests"
          className="i-lift mt-6 flex h-12 items-center justify-between rounded-xl bg-white px-5 text-sm font-bold text-[#2d2080] hover:bg-white/90"
        >
          <span className="inline-flex items-center gap-2">
            <Play className="h-4 w-4 fill-current" /> Browse tests
          </span>
          <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    );
  }

  const pct = c.question_count ? (100 * c.answered) / c.question_count : 0;
  return (
    <div className="flex h-full flex-col justify-between rounded-2xl bg-gradient-to-br from-[#4b3bc4] via-[#3a2b9e] to-[#241a63] p-6 text-white">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-white/60">Continue learning</p>
        <h3 className="mt-3 line-clamp-2 text-[22px] font-bold leading-tight">{c.test_title}</h3>
        <p className="mt-1.5 text-sm text-white/70">
          {c.sections.join(" · ") || "Full syllabus"} · {c.question_count} questions
        </p>
      </div>

      <div className="mt-6">
        <div className="flex items-center justify-between text-sm">
          <span className="text-white/70">Progress</span>
          <span className="font-semibold tabular-nums">
            {c.answered} / {c.question_count}
          </span>
        </div>
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/20">
          <div className="h-full rounded-full bg-white transition-all" style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-3 flex items-center justify-between text-xs text-white/65">
          <span className="inline-flex items-center gap-1.5">
            <Clock className="h-3.5 w-3.5" />
            {c.expired ? "Time expired" : `${hhmmss(c.seconds_left)} left`}
          </span>
          <span>{sinceLabel(c.started_at)}</span>
        </div>
      </div>

      <Link
        href={`/attempt/${c.attempt_id}`}
        className="i-lift mt-5 flex h-12 items-center justify-between rounded-xl bg-white px-5 text-sm font-bold text-[#2d2080] hover:bg-white/90"
      >
        <span className="inline-flex items-center gap-2">
          <Play className="h-4 w-4 fill-current" /> {c.expired ? "Submit test" : "Resume test"}
        </span>
        <ArrowRight className="h-4 w-4" />
      </Link>
    </div>
  );
}

/* ---------------------------------------------------------------- stat tiles */

function Stat({
  icon,
  tint,
  label,
  value,
  sub,
  subTone = "text-subtle",
}: {
  icon: React.ReactNode;
  tint: string;
  label: string;
  value: React.ReactNode;
  sub: React.ReactNode;
  subTone?: string;
}) {
  return (
    <Card className="flex items-center gap-4 p-5">
      <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${tint}`}>{icon}</span>
      <div className="min-w-0">
        <p className="text-[13px] text-muted">{label}</p>
        <p className="mt-0.5 text-[26px] font-bold leading-none tracking-tight tabular-nums">{value}</p>
        <p className={`mt-1.5 text-[11px] font-medium ${subTone}`}>{sub}</p>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------- donut */

function Donut({ pct, size = 170 }: { pct: number; size?: number }) {
  const stroke = 22;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, pct));
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} className="fill-none stroke-brand-soft" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeWidth={stroke}
          strokeLinecap="round"
          className="fill-none stroke-brand"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - v / 100)}
          style={{ transition: "stroke-dashoffset 1s cubic-bezier(0.22,1,0.36,1)" }}
        />
      </svg>
      <div className="absolute text-center">
        <div className="text-[28px] font-bold leading-none tabular-nums">{Math.round(v)}%</div>
        <div className="mt-1 text-xs text-subtle">solved</div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------- page */

export default function DashboardPage() {
  const { data, loading } = useApi<Dashboard>("/api/dashboard");

  if (loading || !data)
    return (
      <div className="space-y-6">
        <Skeleton className="h-12 w-80" />
        <div className="grid gap-5 lg:grid-cols-[1.55fr_1fr]">
          <Skeleton className="h-[420px]" />
          <Skeleton className="h-[420px]" />
        </div>
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-80" />
      </div>
    );

  const t = data.totals;
  const pyqRemaining = Math.max(0, data.pyq.total - data.pyq.solved);
  const pyqPct = data.pyq.total ? (100 * data.pyq.solved) / data.pyq.total : 0;
  const trend = data.trend.map((p) => ({
    ...p,
    label: p.date ? new Date(p.date).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "",
  }));

  return (
    <>
      {/* greeting + streak */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-bold tracking-[0.12em] text-subtle">{today()}</p>
          <h1 className="mt-2 text-[40px] font-bold leading-[1.1] tracking-tight sm:text-[44px]">
            {greeting()}, {data.user.name.split(" ")[0]}.
          </h1>
          <p className="mt-2 text-[15px] text-muted">Your next breakthrough is one focused session away.</p>
        </div>
        <Card className="flex items-center gap-3 px-5 py-4">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-warning-soft text-warning">
            <Flame className="h-[18px] w-[18px]" />
          </span>
          <div>
            <p className="text-[15px] font-bold leading-none">
              {data.streak.current} day streak
            </p>
            <p className="mt-1.5 text-xs text-subtle">Personal best: {data.streak.best} days</p>
          </div>
        </Card>
      </div>

      <ExamCountdown />

      {/* hero row */}
      <div className="mt-5 grid gap-5 lg:grid-cols-[1.55fr_1fr]">
        <PracticeActivity data={data} />
        <ContinueCard data={data} />
      </div>

      {/* stat tiles */}
      <div className="mt-5 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          icon={<Target className="h-[18px] w-[18px] text-brand" />}
          tint="bg-brand-soft"
          label="Tests completed"
          value={t.tests_taken}
          sub={t.tests_this_week ? `+${t.tests_this_week} this week` : "No tests this week"}
          subTone={t.tests_this_week ? "text-success" : "text-subtle"}
        />
        <Stat
          icon={<TrendingUp className="h-[18px] w-[18px] text-success" />}
          tint="bg-success-soft"
          label="Average score"
          value={`${t.avg_percent}%`}
          sub={
            t.avg_delta_30d === null
              ? "across all tests"
              : `${t.avg_delta_30d >= 0 ? "+" : ""}${t.avg_delta_30d}% vs last month`
          }
          subTone={t.avg_delta_30d === null ? "text-subtle" : t.avg_delta_30d >= 0 ? "text-success" : "text-danger"}
        />
        <Stat
          icon={<Clock className="h-[18px] w-[18px] text-info" />}
          tint="bg-info/10"
          label="Study time"
          value={`${t.hours_practiced}h`}
          sub={`${t.hours_this_week}h this week`}
          subTone="text-info"
        />
        <Stat
          icon={<BookOpen className="h-[18px] w-[18px] text-warning" />}
          tint="bg-warning-soft"
          label="PYQs solved"
          value={data.pyq.solved}
          sub={`${pyqRemaining} remaining`}
          subTone="text-warning"
        />
      </div>

      {/* performance + pyq */}
      <div className="mt-5 grid gap-5 lg:grid-cols-[1.55fr_1fr]">
        <Card className="h-full p-6">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-[17px] font-bold tracking-tight">Performance overview</h2>
              <p className="mt-1 text-sm text-muted">Your score trend across recent tests</p>
            </div>
          </div>
          {trend.length ? (
            <div className="h-[260px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trend} margin={{ left: -22, right: 12, top: 12, bottom: 4 }}>
                  <defs>
                    <linearGradient id="dash-score" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.26} />
                      <stop offset="100%" stopColor="var(--brand)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis
                    dataKey="label"
                    tick={{ fontSize: 11, fill: "var(--fg-subtle)" }}
                    axisLine={false}
                    tickLine={false}
                    minTickGap={28}
                  />
                  <YAxis
                    domain={[0, 100]}
                    ticks={[0, 25, 50, 75, 100]}
                    tick={{ fontSize: 11, fill: "var(--fg-subtle)" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    labelFormatter={(_, p) => p?.[0]?.payload?.test_title ?? ""}
                    formatter={(v) => [`${v ?? 0}%`, "Score"]}
                  />
                  <ReferenceLine
                    y={t.avg_percent}
                    stroke="var(--fg-subtle)"
                    strokeDasharray="4 4"
                    label={{
                      value: `Avg. ${t.avg_percent}%`,
                      position: "insideTopRight",
                      fontSize: 11,
                      fill: "var(--fg-subtle)",
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="percent"
                    stroke="var(--brand)"
                    strokeWidth={2.5}
                    fill="url(#dash-score)"
                    dot={{ r: 4, fill: "var(--bg-elev)", stroke: "var(--brand)", strokeWidth: 2.5 }}
                    activeDot={{ r: 6 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex h-[260px] flex-col items-center justify-center rounded-2xl border border-dashed border-line text-center">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-soft text-brand">
                <TrendingUp className="h-5 w-5" />
              </span>
              <p className="mt-4 text-[15px] font-semibold">No tests yet</p>
              <p className="mt-1 text-sm text-muted">Your score trend appears after your first test.</p>
            </div>
          )}
        </Card>

        <Card className="flex h-full flex-col p-6">
          <div className="flex items-start justify-between gap-3">
            <h2 className="text-[17px] font-bold tracking-tight">PYQ progress</h2>
            <Link
              href="/pyq"
              className="inline-flex items-center gap-1 text-[13px] font-semibold text-brand transition-all hover:gap-2"
            >
              View all <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
          <p className="mt-1 text-sm text-muted">Previous-year questions · all subjects</p>

          <div className="my-6 flex items-center justify-center gap-7">
            <Donut pct={pyqPct} />
            <div className="space-y-3">
              <div className="flex items-center gap-2.5 text-sm">
                <span className="h-2.5 w-2.5 rounded-full bg-brand" />
                <span className="text-muted">Solved</span>
                <span className="ml-auto font-bold tabular-nums">{data.pyq.solved}</span>
              </div>
              <div className="flex items-center gap-2.5 text-sm">
                <span className="h-2.5 w-2.5 rounded-full bg-brand-soft" />
                <span className="text-muted">Remaining</span>
                <span className="ml-auto font-bold tabular-nums">{pyqRemaining}</span>
              </div>
            </div>
          </div>

          <Link
            href="/pyq"
            className="i-lift mt-auto flex h-12 items-center justify-center gap-2 rounded-xl bg-brand-soft text-sm font-bold text-brand hover:brightness-95"
          >
            Continue solving <ArrowRight className="h-4 w-4" />
          </Link>
        </Card>
      </div>

      {/* recent attempts */}
      <Card className="mt-5 p-6">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-[17px] font-bold tracking-tight">Recent attempts</h2>
            <p className="mt-1 text-sm text-muted">Review scores and dive deeper into your performance</p>
          </div>
          <Link
            href="/history"
            className="inline-flex items-center gap-1 text-[13px] font-semibold text-brand transition-all hover:gap-2"
          >
            View all attempts <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        {data.recent.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse">
              <thead>
                <tr className="border-b border-line text-left">
                  {["Test", "Score", "Accuracy", "Attempted", ""].map((h) => (
                    <th key={h} className="pb-3 text-[11px] font-bold tracking-[0.08em] text-subtle">
                      {h.toUpperCase()}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.recent.map((r) => (
                  <tr key={r.attempt_id} className="i-row group border-b border-line last:border-0">
                    <td className="py-4 pr-4">
                      <div className="flex items-center gap-3">
                        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand">
                          <FileText className="h-[18px] w-[18px]" />
                        </span>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold">{r.test_title}</p>
                          <p className="truncate text-xs text-subtle">
                            {r.sections?.join(" · ") || "General"}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="py-4 pr-4 text-sm font-semibold tabular-nums">
                      {Math.round(r.score)}/{Math.round(r.max_score)}
                    </td>
                    <td className="py-4 pr-4">
                      <div className="flex items-center gap-2.5">
                        <span className="h-1.5 w-16 overflow-hidden rounded-full bg-sunken">
                          <span
                            className="block h-full rounded-full bg-success"
                            style={{ width: `${Math.max(0, Math.min(100, r.accuracy))}%` }}
                          />
                        </span>
                        <span className="text-sm font-medium tabular-nums">{Math.round(r.accuracy)}%</span>
                      </div>
                    </td>
                    <td className="py-4 pr-4 text-sm text-muted">{formatDate(r.date)}</td>
                    <td className="py-4 text-right">
                      <Link
                        href={`/results/${r.attempt_id}`}
                        className="inline-flex items-center gap-1 text-[13px] font-semibold text-brand transition-all hover:gap-2"
                      >
                        Analyze <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-line py-14 text-center">
            <span className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-soft text-brand">
              <FileText className="h-5 w-5" />
            </span>
            <p className="mt-4 text-[15px] font-semibold">No attempts yet</p>
            <p className="mt-1 text-sm text-muted">Finish a test and it will show up here.</p>
            <Link
              href="/tests"
              className="i-lift mt-5 inline-flex h-10 items-center gap-2 rounded-xl bg-brand px-5 text-sm font-semibold text-white hover:brightness-110"
            >
              Browse tests <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        )}
      </Card>
    </>
  );
}
