"use client";

import { CalendarClock, Check, Pencil, Plus, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api, type ExamTarget } from "@/lib/api";

import { Card } from "./ui";

const MAX_TARGETS = 6;

/** Whole units left until local midnight of `YYYY-MM-DD`. */
function remaining(targetDate: string) {
  const [y, m, d] = targetDate.split("-").map(Number);
  const diff = new Date(y, m - 1, d, 0, 0, 0, 0).getTime() - Date.now();
  const s = Math.max(0, Math.floor(diff / 1000));
  return {
    past: diff <= 0,
    days: Math.floor(s / 86400),
    hours: Math.floor((s % 86400) / 3600),
    minutes: Math.floor((s % 3600) / 60),
    seconds: s % 60,
  };
}

function prettyDate(targetDate: string) {
  return new Date(`${targetDate}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function Unit({ value, label }: { value: number; label: string }) {
  return (
    <div className="flex flex-col items-center">
      <span className="min-w-[2.4ch] text-center text-[26px] font-bold leading-none tracking-tight tabular-nums sm:text-[30px]">
        {String(value).padStart(2, "0")}
      </span>
      <span className="mt-1.5 text-[10px] font-semibold tracking-[0.1em] text-subtle">{label}</span>
    </div>
  );
}

function Colon() {
  return <span className="self-start pt-0.5 text-[22px] font-bold leading-none text-line sm:text-[26px]">:</span>;
}

function TargetForm({
  initial,
  onSave,
  onCancel,
  busy,
  error,
}: {
  initial?: ExamTarget;
  onSave: (name: string, date: string) => void;
  onCancel: () => void;
  busy: boolean;
  error: string | null;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [date, setDate] = useState(initial?.target_date ?? "");
  const [local, setLocal] = useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !date) {
      setLocal("Add both an exam name and a date.");
      return;
    }
    setLocal(null);
    onSave(name.trim(), date);
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
      <label className="min-w-[200px] flex-1">
        <span className="mb-1.5 block text-[11px] font-semibold text-muted">Exam name</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="UPSC Prelims 2027"
          maxLength={120}
          autoFocus
          className="h-10 w-full rounded-xl border border-line bg-elev px-3 text-sm outline-none transition-all duration-200 placeholder:text-subtle focus:border-brand focus:ring-4 focus:ring-brand/12"
        />
      </label>
      <label>
        <span className="mb-1.5 block text-[11px] font-semibold text-muted">Target date</span>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="h-10 rounded-xl border border-line bg-elev px-3 text-sm outline-none transition-all duration-200 focus:border-brand focus:ring-4 focus:ring-brand/12"
        />
      </label>
      <button
        type="submit"
        disabled={busy}
        className="i-lift inline-flex h-10 items-center gap-2 rounded-xl bg-brand px-4 text-sm font-semibold text-white hover:brightness-110 disabled:opacity-50"
      >
        <Check className="h-4 w-4" /> {busy ? "Saving…" : initial ? "Save" : "Start countdown"}
      </button>
      <button
        type="button"
        onClick={onCancel}
        className="inline-flex h-10 items-center gap-1.5 rounded-xl border border-line px-3 text-sm font-medium text-muted transition hover:text-fg"
      >
        <X className="h-4 w-4" /> Cancel
      </button>
      {(local || error) && <p className="w-full text-xs font-medium text-danger">{local ?? error}</p>}
    </form>
  );
}

function TargetRow({
  target,
  onEdit,
  onDelete,
}: {
  target: ExamTarget;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const left = remaining(target.target_date);
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-4 py-4 first:pt-0 last:pb-0">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand">
          <CalendarClock className="h-[18px] w-[18px]" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-[16px] font-bold tracking-tight">{target.name}</p>
          <p className="mt-0.5 text-xs text-muted">
            {left.past ? `Was on ${prettyDate(target.target_date)}` : prettyDate(target.target_date)}
          </p>
        </div>
      </div>

      {left.past ? (
        <p className="text-sm font-semibold text-muted">The day has arrived — good luck.</p>
      ) : (
        <div className="flex items-start gap-3 sm:gap-4">
          <Unit value={left.days} label="DAYS" />
          <Colon />
          <Unit value={left.hours} label="HOURS" />
          <Colon />
          <Unit value={left.minutes} label="MINUTES" />
          <Colon />
          <Unit value={left.seconds} label="SECONDS" />
        </div>
      )}

      <div className="flex items-center gap-2">
        <button
          onClick={onEdit}
          aria-label={`Edit ${target.name}`}
          className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-line px-3 text-xs font-medium text-muted transition hover:text-fg"
        >
          <Pencil className="h-3.5 w-3.5" /> Edit
        </button>
        <button
          onClick={onDelete}
          aria-label={`Remove ${target.name}`}
          className="grid h-9 w-9 place-items-center rounded-xl border border-line text-subtle transition hover:border-danger/40 hover:text-danger"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

export function ExamCountdown() {
  const [targets, setTargets] = useState<ExamTarget[]>([]);
  const [ready, setReady] = useState(false);
  /** null = not editing, "new" = adding, number = editing that id. */
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [, setTick] = useState(0);

  const load = () =>
    api<ExamTarget[]>("/api/exam-targets")
      .then(setTargets)
      .catch(() => {});

  useEffect(() => {
    let live = true;
    api<ExamTarget[]>("/api/exam-targets")
      .then((t) => live && setTargets(t))
      .catch(() => {})
      .finally(() => live && setReady(true));
    return () => {
      live = false;
    };
  }, []);

  // One tick a second drives every row's seconds column.
  useEffect(() => {
    if (!targets.length) return;
    const id = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [targets.length]);

  async function save(name: string, target_date: string) {
    setBusy(true);
    setError(null);
    try {
      if (editing === "new") {
        await api("/api/exam-targets", { method: "POST", json: { name, target_date } });
      } else {
        await api(`/api/exam-targets/${editing}`, { method: "PUT", json: { name, target_date } });
      }
      await load();
      setEditing(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    try {
      await api(`/api/exam-targets/${id}`, { method: "DELETE" });
    } catch {
      /* already gone */
    }
    await load();
    if (editing === id) setEditing(null);
  }

  if (!ready) return null;

  const editTarget = typeof editing === "number" ? targets.find((t) => t.id === editing) : undefined;

  return (
    <Card className="mt-6 p-5">
      {targets.length === 0 && editing === null ? (
        <div className="flex flex-wrap items-center gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand">
            <CalendarClock className="h-[18px] w-[18px]" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-[15px] font-bold tracking-tight">Set your exam countdown</h2>
            <p className="text-xs text-muted">Name the exam and pick the date — the timer lives here on your Overview.</p>
          </div>
          <button
            onClick={() => setEditing("new")}
            className="i-lift inline-flex h-10 items-center gap-2 rounded-xl bg-brand px-4 text-sm font-semibold text-white hover:brightness-110"
          >
            <Plus className="h-4 w-4" /> Add a timer
          </button>
        </div>
      ) : (
        <>
          <div className="divide-y divide-line">
            {targets.map((t) =>
              editing === t.id ? (
                <div key={t.id} className="py-4 first:pt-0 last:pb-0">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <p className="text-[13px] font-semibold text-muted">Editing this countdown</p>
                    <button
                      onClick={() => remove(t.id)}
                      className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line px-2.5 text-xs font-medium text-muted transition hover:border-danger/40 hover:text-danger"
                    >
                      <Trash2 className="h-3.5 w-3.5" /> Remove
                    </button>
                  </div>
                  <TargetForm
                    initial={editTarget}
                    onSave={save}
                    onCancel={() => setEditing(null)}
                    busy={busy}
                    error={error}
                  />
                </div>
              ) : (
                <TargetRow key={t.id} target={t} onEdit={() => setEditing(t.id)} onDelete={() => remove(t.id)} />
              ),
            )}
          </div>

          {editing === "new" && (
            <div className={targets.length ? "mt-4 border-t border-line pt-4" : ""}>
              <p className="mb-3 text-[13px] font-semibold text-muted">New countdown</p>
              <TargetForm onSave={save} onCancel={() => setEditing(null)} busy={busy} error={error} />
            </div>
          )}

          {editing === null && (
            <div className="mt-4 border-t border-line pt-4">
              {targets.length < MAX_TARGETS ? (
                <button
                  onClick={() => setEditing("new")}
                  className="i-nav inline-flex items-center gap-1.5 rounded-lg text-[13px] font-semibold text-brand"
                >
                  <Plus className="h-4 w-4" /> Add another timer
                </button>
              ) : (
                <p className="text-xs text-subtle">You are tracking the maximum of {MAX_TARGETS} exams.</p>
              )}
            </div>
          )}
        </>
      )}
    </Card>
  );
}
