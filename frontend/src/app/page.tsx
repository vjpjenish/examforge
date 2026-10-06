"use client";

import {
  ArrowRight,
  BarChart3,
  BookOpenCheck,
  Brain,
  FileScan,
  Layers,
  ShieldCheck,
  Timer,
  Wand2,
} from "lucide-react";
import { motion } from "motion/react";

import { Logo, ThemeToggle } from "@/components/AppShell";
import { Button, Card, Reveal } from "@/components/ui";
import { useAuth } from "@/lib/auth";

const FEATURES = [
  {
    icon: FileScan,
    title: "Any PDF, any format",
    body: "Gemini vision reads each page like a human: two columns, bilingual papers, scanned copies, answer keys at the back.",
  },
  {
    icon: ShieldCheck,
    title: "Self-checking extraction",
    body: "A validator cross-checks options, numbering and answer keys, then a stronger model re-reads every doubtful question.",
  },
  {
    icon: Wand2,
    title: "Admin review studio",
    body: "Flagged questions surface first, side by side with their source page. Fix, approve, and publish in minutes.",
  },
  {
    icon: Timer,
    title: "Real exam simulation",
    body: "Server-timed tests with sections, mark-for-review, a question palette and configurable negative marking.",
  },
  {
    icon: BarChart3,
    title: "Deep analytics",
    body: "Score, accuracy, negative marks, section-wise splits, time on every question, rank and percentile.",
  },
  {
    icon: BookOpenCheck,
    title: "PYQ bank",
    body: "Every previous-year question, filterable by subject and year, with solved / unsolved and bookmark tracking.",
  },
];

const STEPS = [
  ["Upload", "Drop a test series or PYQ PDF."],
  ["Understand", "AI profiles the layout, sections and answer key."],
  ["Extract", "Pages are read in overlapping windows, in parallel."],
  ["Verify", "Doubtful questions are re-checked and flagged for review."],
  ["Practise", "Publish as a timed test or add to the PYQ bank."],
];

export default function Landing() {
  const { user } = useAuth();
  const cta = user ? { href: "/dashboard", label: "Open dashboard" } : { href: "/register", label: "Get started free" };

  return (
    <div className="relative overflow-hidden">
      <div className="bg-grid pointer-events-none absolute inset-x-0 top-0 h-[640px]" />
      <div className="pointer-events-none absolute -top-40 left-1/2 h-[520px] w-[900px] -translate-x-1/2 rounded-full bg-gradient-to-r from-brand/25 via-brand-2/20 to-pink-500/15 blur-3xl" />

      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <Logo />
        <div className="flex items-center gap-2">
          <ThemeToggle />
          {!user && (
            <Button variant="ghost" href="/login">
              Sign in
            </Button>
          )}
          <Button href={cta.href}>{user ? "Dashboard" : "Sign up"}</Button>
        </div>
      </header>

      <section className="relative z-10 mx-auto max-w-6xl px-4 pb-20 pt-16 text-center sm:px-6 sm:pt-24">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-elev/70 px-3 py-1 text-xs font-medium text-muted backdrop-blur">
            <Brain className="h-3.5 w-3.5 text-brand" /> Powered by Google Gemini
          </span>
        </motion.div>
        <motion.h1
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.05 }}
          className="mx-auto mt-6 max-w-3xl text-4xl font-semibold tracking-tight sm:text-6xl"
        >
          Turn any exam PDF into a <span className="text-gradient">smart online test</span>
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.12 }}
          className="mx-auto mt-5 max-w-2xl text-base text-muted sm:text-lg"
        >
          Upload test series and previous-year papers from any institute. ExamForge extracts every question, option,
          answer, explanation and diagram, then lets students practise with real exam timing and detailed analysis.
        </motion.p>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="mt-8 flex flex-wrap justify-center gap-3"
        >
          <Button size="lg" href={cta.href}>
            {cta.label} <ArrowRight className="h-4 w-4" />
          </Button>
          <Button size="lg" variant="secondary" href="#how">
            How extraction works
          </Button>
        </motion.div>

        <Reveal delay={0.25} className="mx-auto mt-16 max-w-4xl">
          <Card className="overflow-hidden p-0 text-left">
            <div className="flex items-center gap-1.5 border-b border-line px-4 py-3">
              <span className="h-2.5 w-2.5 rounded-full bg-danger/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-warning/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-success/70" />
              <span className="ml-3 text-xs text-subtle">mock-test-07.pdf · 48 pages</span>
            </div>
            <div className="grid gap-0 sm:grid-cols-2">
              <div className="space-y-2 border-b border-line p-6 sm:border-b-0 sm:border-r">
                {[92, 78, 85, 60, 88, 70, 40].map((w, i) => (
                  <motion.div
                    key={i}
                    className="h-2.5 rounded-full bg-sunken"
                    style={{ width: `${w}%` }}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.4 + i * 0.05 }}
                  />
                ))}
                <div className="mt-4 h-24 rounded-xl border border-dashed border-brand/40 bg-brand-soft/40" />
              </div>
              <div className="space-y-3 p-6 font-mono text-xs">
                <p className="text-subtle">{"// extracted"}</p>
                <p>
                  <span className="text-brand">number</span>: &quot;14&quot;, <span className="text-brand">section</span>:
                  &quot;Physics&quot;
                </p>
                <p>
                  <span className="text-brand">options</span>: [A, B, C, D]
                </p>
                <p>
                  <span className="text-brand">answer</span>: [&quot;C&quot;] <span className="text-subtle">← answer key, p.46</span>
                </p>
                <p>
                  <span className="text-brand">figure</span>: circuit.png
                </p>
                <p>
                  <span className="text-brand">confidence</span>: <span className="text-success">0.97 ✓ verified</span>
                </p>
              </div>
            </div>
          </Card>
        </Reveal>
      </section>

      <section className="relative z-10 mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <Reveal className="mb-12 text-center">
          <h2 className="text-3xl font-semibold tracking-tight">Everything a serious aspirant needs</h2>
          <p className="mt-2 text-muted">Built for JEE, NEET, UPSC, SSC, banking and every exam in between.</p>
        </Reveal>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, body }, i) => (
            <Reveal key={title} delay={i * 0.05}>
              <Card className="h-full p-6 transition-transform duration-300 hover:-translate-y-1">
                <div className="mb-4 grid h-10 w-10 place-items-center rounded-xl bg-brand-soft text-brand">
                  <Icon className="h-5 w-5" />
                </div>
                <h3 className="font-semibold">{title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{body}</p>
              </Card>
            </Reveal>
          ))}
        </div>
      </section>

      <section id="how" className="relative z-10 mx-auto max-w-6xl scroll-mt-10 px-4 py-20 sm:px-6">
        <Reveal className="mb-12 text-center">
          <h2 className="text-3xl font-semibold tracking-tight">The extraction pipeline</h2>
          <p className="mt-2 text-muted">No templates. Every PDF is understood on its own terms.</p>
        </Reveal>
        <div className="grid gap-4 md:grid-cols-5">
          {STEPS.map(([title, body], i) => (
            <Reveal key={title} delay={i * 0.07}>
              <div className="relative h-full rounded-2xl border border-line bg-elev p-5">
                <span className="text-xs font-semibold text-brand">0{i + 1}</span>
                <h3 className="mt-2 font-semibold">{title}</h3>
                <p className="mt-1 text-sm text-muted">{body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="relative z-10 mx-auto max-w-6xl px-4 pb-24 sm:px-6">
        <Reveal>
          <Card className="relative overflow-hidden p-10 text-center">
            <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-brand/10 via-transparent to-brand-2/10" />
            <Layers className="mx-auto h-8 w-8 text-brand" />
            <h2 className="mt-4 text-2xl font-semibold tracking-tight sm:text-3xl">Start practising smarter today</h2>
            <p className="mx-auto mt-2 max-w-lg text-muted">
              Thousands of questions, one consistent experience, whichever institute wrote the paper.
            </p>
            <Button size="lg" href={cta.href} className="mt-6">
              {cta.label} <ArrowRight className="h-4 w-4" />
            </Button>
          </Card>
        </Reveal>
      </section>

      <footer className="border-t border-line py-8 text-center text-xs text-subtle">
        © {new Date().getFullYear()} ExamForge
      </footer>
    </div>
  );
}
