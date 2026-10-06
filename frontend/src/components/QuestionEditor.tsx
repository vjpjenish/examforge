"use client";

import { Check, Pencil, Plus, Trash2, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";

import { RichText } from "@/components/RichText";
import { Button, Card, ErrorNote, Field, Input, Select, Skeleton, Textarea } from "@/components/ui";
import { api, type Option, type Question, type QuestionType } from "@/lib/api";

function answerToText(q: Question) {
  if (q.type === "numerical") return q.answer && !Array.isArray(q.answer) ? String(q.answer.raw ?? q.answer.value ?? "") : "";
  return Array.isArray(q.answer) ? q.answer.join(",") : "";
}

/** Edit a question's content. Saving marks it as corrected by a person; re-extraction keeps the edit. */
export function QuestionEditor({ q, onSaved, onCancel }: { q: Question; onSaved: (q: Question) => void; onCancel: () => void }) {
  const [draft, setDraft] = useState({
    text: q.text,
    type: q.type,
    section: q.section,
    topic: q.topic ?? "",
    options: q.options.map((o) => ({ ...o })),
    answer: answerToText(q),
    explanation: q.explanation ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    let answer: unknown = null;
    if (draft.type === "numerical") {
      const v = parseFloat(draft.answer);
      answer = draft.answer.trim() ? (Number.isNaN(v) ? { raw: draft.answer } : { value: v, tolerance: 0.01 }) : null;
    } else if (draft.answer.trim()) {
      answer = draft.answer
        .split(/[,\s]+/)
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean)
        .sort();
    }
    try {
      const saved = await api<Question>(`/api/questions/${q.id}`, {
        method: "PATCH",
        json: {
          text: draft.text,
          type: draft.type,
          section: draft.section,
          topic: draft.topic || null,
          options: draft.type.startsWith("mcq") ? draft.options : [],
          answer,
          explanation: draft.explanation || null,
        },
      });
      onSaved(saved);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  const setOpt = (i: number, patch: Partial<Option>) =>
    setDraft((d) => ({ ...d, options: d.options.map((o, j) => (j === i ? { ...o, ...patch } : o)) }));

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Type">
          <Select value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value as QuestionType })}>
            <option value="mcq_single">Single correct</option>
            <option value="mcq_multi">Multiple correct</option>
            <option value="numerical">Numerical</option>
            <option value="subjective">Subjective</option>
          </Select>
        </Field>
        <Field label="Section">
          <Input value={draft.section} onChange={(e) => setDraft({ ...draft, section: e.target.value })} />
        </Field>
        <Field label="Topic">
          <Input value={draft.topic} onChange={(e) => setDraft({ ...draft, topic: e.target.value })} />
        </Field>
      </div>
      <Field label="Question text" hint="Markdown with LaTeX: $x^2$ inline, $$...$$ block, | tables |">
        <Textarea rows={6} value={draft.text} onChange={(e) => setDraft({ ...draft, text: e.target.value })} className="font-mono text-[13px]" />
      </Field>
      {draft.text && (
        <div className="rounded-xl border border-dashed border-line p-3">
          <p className="mb-1 text-[11px] uppercase tracking-wider text-subtle">Preview</p>
          <RichText text={draft.text} className="text-sm" />
        </div>
      )}
      {draft.type.startsWith("mcq") && (
        <div className="space-y-2">
          <span className="text-sm font-medium">Options</span>
          {draft.options.map((o, i) => (
            <div key={i} className="flex gap-2">
              <Input value={o.label} onChange={(e) => setOpt(i, { label: e.target.value.toUpperCase() })} className="w-14 text-center" aria-label="Option label" />
              <Input value={o.text} onChange={(e) => setOpt(i, { text: e.target.value })} aria-label={`Option ${o.label} text`} />
              <Button variant="ghost" size="sm" aria-label="Remove option" onClick={() => setDraft({ ...draft, options: draft.options.filter((_, j) => j !== i) })}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              setDraft({ ...draft, options: [...draft.options, { label: String.fromCharCode(65 + draft.options.length), text: "", image: null }] })
            }
          >
            <Plus className="h-4 w-4" /> Add option
          </Button>
        </div>
      )}
      <Field
        label="Correct answer"
        hint={draft.type === "numerical" ? "A number, or a range like 2.5 to 2.7. Leave empty if unknown." : "Option labels, e.g. B or A,C. Leave empty if unknown."}
      >
        <Input value={draft.answer} onChange={(e) => setDraft({ ...draft, answer: e.target.value })} />
      </Field>
      <Field label="Explanation">
        <Textarea rows={4} value={draft.explanation} onChange={(e) => setDraft({ ...draft, explanation: e.target.value })} />
      </Field>
      {error && <ErrorNote message={error} />}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button onClick={save} loading={busy}>
          <Check className="h-4 w-4" /> Save
        </Button>
      </div>
    </div>
  );
}

function EditDialog({ questionId, onSaved, onClose }: { questionId: number; onSaved: (q: Question) => void; onClose: () => void }) {
  const [q, setQ] = useState<Question | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Question>(`/api/questions/${questionId}`)
      .then(setQ)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [questionId]);

  return (
    <motion.div
      className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/50 px-4 py-8 backdrop-blur-sm"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div initial={{ scale: 0.97, y: 8 }} animate={{ scale: 1, y: 0 }} className="w-full max-w-2xl" onClick={(e) => e.stopPropagation()}>
        <Card className="p-6">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold">Fix this question</h2>
              <p className="text-sm text-muted">Correct anything the PDF extraction got wrong. Your fix is shared with everyone.</p>
            </div>
            <button onClick={onClose} aria-label="Close" className="rounded-lg p-1 text-subtle hover:bg-sunken hover:text-fg">
              <X className="h-5 w-5" />
            </button>
          </div>
          {error ? (
            <ErrorNote message={error} />
          ) : q ? (
            <QuestionEditor
              q={q}
              onCancel={onClose}
              onSaved={(saved) => {
                onSaved(saved);
                onClose();
              }}
            />
          ) : (
            <Skeleton className="h-72" />
          )}
        </Card>
      </motion.div>
    </motion.div>
  );
}

/** "Fix this question" for students and admins: opens the editor in a dialog. */
export function EditQuestionButton({ questionId, onSaved }: { questionId: number; onSaved: (q: Question) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        <Pencil className="h-4 w-4" /> Fix question
      </Button>
      <AnimatePresence>{open && <EditDialog questionId={questionId} onSaved={onSaved} onClose={() => setOpen(false)} />}</AnimatePresence>
    </>
  );
}
