"use client";

import clsx from "clsx";
import { AlarmClock, ChevronLeft, ChevronRight, Eraser, Flag, LayoutGrid, Send, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { QuestionView, type Response } from "@/components/QuestionView";
import { Button, Card, ErrorNote, Spinner } from "@/components/ui";
import { api, type AttemptQuestion, type AttemptState } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";

type Status = "not_visited" | "not_answered" | "answered" | "marked" | "answered_marked";

const isAnswered = (r: Response) => (Array.isArray(r) ? r.length > 0 : !!r);

function statusOf(q: AttemptQuestion): Status {
  const answered = isAnswered(q.response);
  if (q.marked_for_review) return answered ? "answered_marked" : "marked";
  if (answered) return "answered";
  return q.visited ? "not_answered" : "not_visited";
}

const STATUS_STYLE: Record<Status, string> = {
  not_visited: "bg-sunken text-muted border-line",
  not_answered: "bg-danger-soft text-danger border-danger/40",
  answered: "bg-success text-white border-success",
  marked: "bg-brand-2 text-white border-brand-2",
  answered_marked: "bg-brand-2 text-white border-brand-2 ring-2 ring-success ring-offset-1 ring-offset-elev",
};
const STATUS_LABEL: Record<Status, string> = {
  not_visited: "Not visited",
  not_answered: "Not answered",
  answered: "Answered",
  marked: "Marked for review",
  answered_marked: "Answered & marked",
};

function Clock({ deadline, offset, onExpire }: { deadline: number; offset: number; onExpire: () => void }) {
  const [now, setNow] = useState(() => Date.now() + offset);
  const fired = useRef(false);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() + offset), 500);
    return () => clearInterval(t);
  }, [offset]);
  const left = Math.max(0, Math.floor((deadline - now) / 1000));
  useEffect(() => {
    if (left === 0 && !fired.current) {
      fired.current = true;
      onExpire();
    }
  }, [left, onExpire]);
  const h = Math.floor(left / 3600);
  const m = Math.floor((left % 3600) / 60);
  const s = left % 60;
  const urgent = left < 300;
  return (
    <div
      className={clsx(
        "flex items-center gap-2 rounded-xl px-3 py-1.5 font-mono text-sm font-semibold tabular-nums transition-colors",
        urgent ? "animate-pulse bg-danger-soft text-danger" : "bg-sunken text-fg",
      )}
    >
      <AlarmClock className="h-4 w-4" />
      {h > 0 && `${h}:`}
      {String(m).padStart(2, "0")}:{String(s).padStart(2, "0")}
    </div>
  );
}

export default function AttemptPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { ready } = useRequireAuth();
  const [state, setState] = useState<AttemptState | null>(null);
  const [questions, setQuestions] = useState<AttemptQuestion[]>([]);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [offset, setOffset] = useState(0);

  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const activeSince = useRef(0);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const submitted = useRef(false);

  const save = useCallback(
    (qid: number, body: Record<string, unknown>) => {
      // Serialise writes so responses never arrive out of order.
      queue.current = queue.current
        .then(() => api(`/api/attempts/${id}/answers/${qid}`, { method: "PUT", json: body }))
        .catch((e) => {
          if (e?.status === 409) router.replace(`/results/${id}`);
        });
      return queue.current;
    },
    [id, router],
  );

  /** Flag a question as visited (locally and on the server) when the student lands on it. */
  const markVisited = useCallback(
    (qs: AttemptQuestion[], i: number) => {
      if (!qs[i] || qs[i].visited) return qs;
      void save(qs[i].question_id, { visited: true });
      return qs.map((q, j) => (j === i ? { ...q, visited: true } : q));
    },
    [save],
  );

  useEffect(() => {
    if (!ready) return;
    api<AttemptState>(`/api/attempts/${id}`)
      .then((s) => {
        if (s.status === "submitted") {
          router.replace(`/results/${id}`);
          return;
        }
        setOffset(new Date(s.server_now).getTime() - Date.now());
        setState(s);
        const first = Math.max(0, s.questions.findIndex((q) => !isAnswered(q.response)));
        setQuestions(markVisited(s.questions, first));
        setIndex(first);
        activeSince.current = Date.now();
      })
      .catch((e) => setError(e.message));
  }, [id, ready, router, markVisited]);

  const current = questions[index];

  /** Bank the time spent on the current question. */
  const flushTime = useCallback(() => {
    if (!current) return;
    const delta = Math.round((Date.now() - activeSince.current) / 1000);
    activeSince.current = Date.now();
    if (delta > 0) {
      setQuestions((qs) => qs.map((q) => (q.question_id === current.question_id ? { ...q, time_spent_seconds: q.time_spent_seconds + delta } : q)));
      void save(current.question_id, { time_spent_delta: Math.min(delta, 3600) });
    }
  }, [current, save]);

  // Periodically bank time, and when the tab is hidden.
  useEffect(() => {
    const t = setInterval(flushTime, 30000);
    const onHide = () => document.visibilityState === "hidden" && flushTime();
    document.addEventListener("visibilitychange", onHide);
    const warn = (e: BeforeUnloadEvent) => {
      if (!submitted.current) e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      clearInterval(t);
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("beforeunload", warn);
    };
  }, [flushTime]);

  const go = (i: number) => {
    if (i < 0 || i >= questions.length || i === index) return;
    flushTime();
    setQuestions((qs) => markVisited(qs, i));
    setIndex(i);
    setPaletteOpen(false);
  };

  const setResponse = (r: Response) => {
    if (!current) return;
    setQuestions((qs) => qs.map((q) => (q.question_id === current.question_id ? { ...q, response: r } : q)));
    if (debounce.current) clearTimeout(debounce.current);
    const qid = current.question_id;
    const send = () => save(qid, { response: r });
    if (current.type === "numerical") debounce.current = setTimeout(send, 500);
    else void send();
  };

  const toggleMark = () => {
    if (!current) return;
    const marked = !current.marked_for_review;
    setQuestions((qs) => qs.map((q) => (q.question_id === current.question_id ? { ...q, marked_for_review: marked } : q)));
    void save(current.question_id, { marked_for_review: marked });
  };

  const submit = useCallback(async () => {
    if (submitted.current) return;
    submitted.current = true;
    setSubmitting(true);
    flushTime();
    try {
      await queue.current;
      await api(`/api/attempts/${id}/submit`, { method: "POST" });
      router.replace(`/results/${id}`);
    } catch (e) {
      submitted.current = false;
      setSubmitting(false);
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [flushTime, id, router]);

  const sections = useMemo(() => {
    const map = new Map<string, number[]>();
    questions.forEach((q, i) => map.set(q.section, [...(map.get(q.section) ?? []), i]));
    return [...map.entries()];
  }, [questions]);

  const counts = useMemo(() => {
    const c: Record<Status, number> = { not_visited: 0, not_answered: 0, answered: 0, marked: 0, answered_marked: 0 };
    questions.forEach((q) => c[statusOf(q)]++);
    return c;
  }, [questions]);

  if (error) return <div className="mx-auto max-w-lg p-10"><ErrorNote message={error} /></div>;
  if (!state || !current)
    return (
      <div className="grid min-h-screen place-items-center">
        <Spinner />
      </div>
    );

  const palette = (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-2 text-[11px]">
        {(Object.keys(STATUS_LABEL) as Status[]).map((s) => (
          <div key={s} className="flex items-center gap-2">
            <span className={clsx("grid h-5 w-5 place-items-center rounded-md border text-[10px]", STATUS_STYLE[s])}>{counts[s]}</span>
            <span className="text-muted">{STATUS_LABEL[s]}</span>
          </div>
        ))}
      </div>
      {sections.map(([name, idxs]) => (
        <div key={name}>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-subtle">{name}</p>
          <div className="grid grid-cols-6 gap-2">
            {idxs.map((i) => (
              <button
                key={i}
                onClick={() => go(i)}
                className={clsx(
                  "h-9 rounded-lg border text-xs font-semibold transition-transform hover:scale-105",
                  STATUS_STYLE[statusOf(questions[i])],
                  i === index && "outline-2 outline-offset-2 outline-brand",
                )}
              >
                {i + 1}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 border-b border-line bg-elev/85 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4">
          <h1 className="min-w-0 flex-1 truncate text-sm font-semibold sm:text-base">{state.test.title}</h1>
          <Clock deadline={new Date(state.deadline_at).getTime()} offset={offset} onExpire={submit} />
          <Button size="sm" variant="secondary" className="lg:hidden" onClick={() => setPaletteOpen(true)} aria-label="Question palette">
            <LayoutGrid className="h-4 w-4" />
          </Button>
          <Button size="sm" onClick={() => setConfirm(true)}>
            <Send className="h-4 w-4" /> <span className="hidden sm:inline">Submit</span>
          </Button>
        </div>
        <div className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4 pb-2">
          {sections.map(([name, idxs]) => (
            <button
              key={name}
              onClick={() => go(idxs[0])}
              className={clsx(
                "relative shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                current.section === name ? "text-brand" : "text-muted hover:text-fg",
              )}
            >
              {current.section === name && (
                <motion.span layoutId="section-tab" className="absolute inset-0 rounded-lg bg-brand-soft" />
              )}
              <span className="relative">{name}</span>
            </button>
          ))}
        </div>
      </header>

      <div className="mx-auto grid w-full max-w-7xl flex-1 gap-6 px-4 py-6 lg:grid-cols-[1fr_320px]">
        <div className="flex flex-col">
          <Card className="flex-1 p-5 sm:p-8">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="rounded-lg bg-brand px-2.5 py-1 text-xs font-semibold text-white">Q {index + 1}</span>
                <span className="text-xs text-subtle">
                  {current.section} · {current.type === "numerical" ? "Numerical" : current.type === "mcq_multi" ? "Multiple correct" : "Single correct"}
                </span>
              </div>
              <span className="text-xs text-subtle">
                +{state.test.marks_correct} / {state.test.marks_incorrect}
              </span>
            </div>
            <AnimatePresence mode="wait">
              <motion.div
                key={current.question_id}
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                transition={{ duration: 0.2 }}
              >
                <QuestionView
                  type={current.type}
                  text={current.text}
                  options={current.options}
                  images={current.images}
                  response={current.response}
                  onChange={setResponse}
                />
              </motion.div>
            </AnimatePresence>
          </Card>

          <div className="sticky bottom-0 mt-4 flex flex-wrap items-center gap-2 rounded-2xl border border-line bg-elev/90 p-3 backdrop-blur-xl">
            <Button variant="ghost" size="sm" onClick={() => setResponse(current.type === "numerical" ? "" : [])}>
              <Eraser className="h-4 w-4" /> Clear
            </Button>
            <Button variant="secondary" size="sm" onClick={toggleMark} className={clsx(current.marked_for_review && "border-brand-2 text-brand-2")}>
              <Flag className="h-4 w-4" /> {current.marked_for_review ? "Unmark" : "Mark for review"}
            </Button>
            <div className="ml-auto flex gap-2">
              <Button variant="secondary" size="sm" onClick={() => go(index - 1)} disabled={index === 0}>
                <ChevronLeft className="h-4 w-4" /> Prev
              </Button>
              <Button size="sm" onClick={() => (index === questions.length - 1 ? setConfirm(true) : go(index + 1))}>
                {index === questions.length - 1 ? "Finish" : "Save & next"} <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        <aside className="hidden lg:block">
          <Card className="sticky top-32 max-h-[calc(100vh-9rem)] overflow-y-auto p-5">{palette}</Card>
        </aside>
      </div>

      <AnimatePresence>
        {paletteOpen && (
          <motion.div className="fixed inset-0 z-40 bg-black/40 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setPaletteOpen(false)}>
            <motion.div
              className="absolute inset-x-0 bottom-0 max-h-[80vh] overflow-y-auto rounded-t-3xl bg-elev p-6"
              initial={{ y: "100%" }}
              animate={{ y: 0 }}
              exit={{ y: "100%" }}
              transition={{ type: "spring", stiffness: 380, damping: 38 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mb-4 flex items-center justify-between">
                <h2 className="font-semibold">Questions</h2>
                <button onClick={() => setPaletteOpen(false)} aria-label="Close">
                  <X className="h-5 w-5" />
                </button>
              </div>
              {palette}
            </motion.div>
          </motion.div>
        )}

        {confirm && (
          <motion.div className="fixed inset-0 z-50 grid place-items-center bg-black/50 px-4 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div initial={{ scale: 0.95, y: 10 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 10 }} className="w-full max-w-md">
              <Card className="p-6">
                <h2 className="text-lg font-semibold">Submit test?</h2>
                <p className="mt-1 text-sm text-muted">You will not be able to change your answers afterwards.</p>
                <div className="mt-5 grid grid-cols-3 gap-3 text-center">
                  <div className="rounded-xl bg-success-soft p-3">
                    <div className="text-xl font-semibold text-success">{counts.answered + counts.answered_marked}</div>
                    <div className="text-[11px] text-muted">Answered</div>
                  </div>
                  <div className="rounded-xl bg-brand-soft p-3">
                    <div className="text-xl font-semibold text-brand">{counts.marked + counts.answered_marked}</div>
                    <div className="text-[11px] text-muted">Marked</div>
                  </div>
                  <div className="rounded-xl bg-sunken p-3">
                    <div className="text-xl font-semibold">{counts.not_answered + counts.not_visited + counts.marked}</div>
                    <div className="text-[11px] text-muted">Unanswered</div>
                  </div>
                </div>
                <div className="mt-6 flex justify-end gap-2">
                  <Button variant="secondary" onClick={() => setConfirm(false)}>
                    Keep going
                  </Button>
                  <Button onClick={submit} loading={submitting}>
                    Submit now
                  </Button>
                </div>
              </Card>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
