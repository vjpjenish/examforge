"use client";

import {
  ArrowRight,
  BookOpen,
  CalendarClock,
  FileText,
  FileUp,
  Flame,
  LayoutGrid,
  LineChart,
  NotebookPen,
  Target,
} from "lucide-react";
import Link from "next/link";

import { Card } from "@/components/ui";
import { useAuth } from "@/lib/auth";

type Step = {
  icon: typeof LayoutGrid;
  title: string;
  body: string;
  points: string[];
  href: string;
  cta: string;
};

const STEPS: Step[] = [
  {
    icon: FileText,
    title: "Pick a test and sit it properly",
    body: "My tests lists every paper that has been published. Each one runs timed, with the marking scheme the paper was set up with.",
    points: [
      "Your answers save as you go, so you can leave and come back.",
      "The question palette shows what you have answered, skipped or marked for review.",
      "Submitting scores it immediately — negative marking included.",
    ],
    href: "/tests",
    cta: "Browse test series",
  },
  {
    icon: LineChart,
    title: "Read the analysis, not just the score",
    body: "Every submitted attempt gets a full breakdown, reachable from Analysis or from the Recent attempts table on your Overview.",
    points: [
      "Section-wise accuracy and time spent per question.",
      "Your rank and percentile against everyone else who sat the paper.",
      "A question-by-question review with the correct answer and explanation.",
    ],
    href: "/history",
    cta: "Open analysis",
  },
  {
    icon: NotebookPen,
    title: "Work through your mistake book",
    body: "Every question you answered wrong, from every test, collects in one place. Questions you skipped are not counted as mistakes.",
    points: [
      "Filter by test or by section to focus one paper at a time.",
      "Each entry shows what you picked against the correct answer.",
      'Practise my mistakes replays them like a test and scores you at the end.',
    ],
    href: "/mistakes",
    cta: "Open mistake book",
  },
  {
    icon: BookOpen,
    title: "Drill previous-year questions by exam",
    body: "The PYQ library is split into workspaces — one per exam — so you only ever see the questions that matter to you.",
    points: [
      "Open a workspace to filter its questions by subject, year or status.",
      "Answer a question to check it instantly and reveal the explanation.",
      "Bookmark anything you want to come back to.",
    ],
    href: "/pyq",
    cta: "Open PYQ library",
  },
  {
    icon: CalendarClock,
    title: "Keep the date in view",
    body: "Your Overview carries a live countdown to each exam you are preparing for, alongside the habits that get you there.",
    points: [
      "Add as many countdowns as you need — they sort soonest first.",
      "The practice heatmap shows every day you sat down for a test.",
      "Your streak and study time update as you go.",
    ],
    href: "/dashboard",
    cta: "Go to Overview",
  },
];

const ADMIN_STEP: Step = {
  icon: FileUp,
  title: "Turn a PDF into a test",
  body: "PDF extraction reads a paper and publishes its questions automatically — as a timed test, or into the PYQ library.",
  points: [
    "Set marks per question, the penalty and the duration while uploading a test series.",
    "Choose an exam so PYQ papers land in their own workspace.",
    "Upload an answer key separately as Solutions to attach answers and explanations.",
    "Open any document to review, edit or reject individual questions.",
  ],
  href: "/admin",
  cta: "Open PDF extraction",
};

function StepCard({ step, index }: { step: Step; index: number }) {
  const Icon = step.icon;
  return (
    <Card className="flex flex-col p-6">
      <div className="flex items-start gap-4">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand">
          <Icon className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-bold tracking-[0.12em] text-subtle">STEP {index}</p>
          <h2 className="mt-1.5 text-[17px] font-bold tracking-tight">{step.title}</h2>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">{step.body}</p>
        </div>
      </div>

      <ul className="mt-4 space-y-2">
        {step.points.map((p) => (
          <li key={p} className="flex gap-2.5 text-sm text-muted">
            <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
            <span className="min-w-0">{p}</span>
          </li>
        ))}
      </ul>

      <Link
        href={step.href}
        className="i-nav mt-5 inline-flex w-fit items-center gap-1.5 rounded-lg text-[13px] font-semibold text-brand"
      >
        {step.cta} <ArrowRight className="h-3.5 w-3.5" />
      </Link>
    </Card>
  );
}

export default function GuidePage() {
  const { user } = useAuth();
  const steps = user?.role === "admin" ? [ADMIN_STEP, ...STEPS] : STEPS;

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <p className="text-[11px] font-bold tracking-[0.12em] text-subtle">GETTING STARTED</p>
          <h1 className="mt-2 text-[34px] font-bold leading-[1.1] tracking-tight sm:text-[38px]">Quick guide</h1>
          <p className="mt-2 text-[15px] text-muted">
            A short tour of how ExamForge fits together — sit a paper, read the analysis, then close the gaps it finds.
          </p>
        </div>
        <Card className="flex items-center gap-3 px-5 py-4">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-warning-soft text-warning">
            <Flame className="h-[18px] w-[18px]" />
          </span>
          <div>
            <p className="text-[15px] font-bold leading-none">{steps.length} steps</p>
            <p className="mt-1.5 text-xs text-subtle">About two minutes to read</p>
          </div>
        </Card>
      </div>

      <div className="mt-7 grid gap-5 lg:grid-cols-2">
        {steps.map((s, i) => (
          <StepCard key={s.title} step={s} index={i + 1} />
        ))}
      </div>

      <Card className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-4 p-6">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand">
          <Target className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[17px] font-bold tracking-tight">The short version</h2>
          <p className="mt-1 text-sm text-muted">
            Sit a test, read the analysis, practise the mistakes it surfaces, and repeat. The Overview keeps score.
          </p>
        </div>
        <Link
          href="/tests"
          className="i-lift inline-flex h-11 shrink-0 items-center gap-2 rounded-xl bg-brand px-5 text-sm font-semibold text-white hover:brightness-110"
        >
          Start a test <ArrowRight className="h-4 w-4" />
        </Link>
      </Card>
    </>
  );
}
