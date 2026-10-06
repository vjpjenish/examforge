"use client";

import clsx from "clsx";
import { Check, X } from "lucide-react";
import { motion } from "motion/react";

import { fileUrl, type Answer, type Figure, type Option, type QuestionType } from "@/lib/api";

import { Figures, RichText } from "./RichText";
import { inputCls } from "./ui";

export type Response = string[] | string | null;

interface Props {
  type: QuestionType;
  text: string;
  options: Option[];
  images: Figure[];
  response: Response;
  onChange?: (r: Response) => void;
  /** When set, show correct/incorrect styling. */
  answer?: Answer;
  disabled?: boolean;
}

export function answerLabels(answer: Answer): string[] {
  return Array.isArray(answer) ? answer : [];
}

export function formatAnswer(answer: Answer): string {
  if (!answer) return "Not available";
  if (Array.isArray(answer)) return answer.join(", ");
  if (answer.raw) return answer.raw;
  return answer.value !== undefined ? String(answer.value) : "Not available";
}

export function QuestionView({ type, text, options, images, response, onChange, answer, disabled }: Props) {
  const reveal = answer !== undefined;
  const correct = new Set(answerLabels(answer ?? null));
  const chosen = new Set(Array.isArray(response) ? response : response ? [response] : []);

  const toggle = (label: string) => {
    if (disabled || !onChange) return;
    if (type === "mcq_multi") {
      const next = new Set(chosen);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      onChange([...next].sort());
    } else {
      onChange(chosen.has(label) ? [] : [label]);
    }
  };

  return (
    <div>
      <RichText text={text} className="text-[15px] text-fg sm:text-base" />
      <Figures images={images} />
      {type === "mcq_multi" && <p className="mt-3 text-xs font-medium text-brand">One or more options may be correct</p>}

      {(type === "mcq_single" || type === "mcq_multi") && (
        <div className="mt-5 grid gap-2.5">
          {options.map((o, i) => {
            const isChosen = chosen.has(o.label);
            const isCorrect = reveal && correct.has(o.label);
            const isWrong = reveal && isChosen && !correct.has(o.label);
            return (
              <motion.button
                key={o.label}
                type="button"
                disabled={disabled}
                onClick={() => toggle(o.label)}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
                whileTap={disabled ? undefined : { scale: 0.99 }}
                className={clsx(
                  "group flex w-full items-start gap-3 rounded-xl border px-4 py-3 text-left transition-colors",
                  isCorrect
                    ? "border-success/60 bg-success-soft"
                    : isWrong
                      ? "border-danger/60 bg-danger-soft"
                      : isChosen
                        ? "border-brand bg-brand-soft"
                        : "border-line bg-elev hover:border-brand/40 hover:bg-sunken",
                  disabled && "cursor-default",
                )}
              >
                <span
                  className={clsx(
                    "mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg text-sm font-semibold transition-colors",
                    isCorrect
                      ? "bg-success text-white"
                      : isWrong
                        ? "bg-danger text-white"
                        : isChosen
                          ? "bg-brand text-white"
                          : "bg-sunken text-muted group-hover:text-fg",
                    type === "mcq_multi" ? "rounded-md" : "rounded-full",
                  )}
                >
                  {isCorrect ? <Check className="h-4 w-4" /> : isWrong ? <X className="h-4 w-4" /> : o.label}
                </span>
                <span className="min-w-0 flex-1">
                  {o.text && <RichText text={o.text} className="text-sm sm:text-[15px]" />}
                  {o.image && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={fileUrl(o.image)} alt={`Option ${o.label}`} className="mt-1 max-h-40 rounded-lg bg-white p-1" />
                  )}
                </span>
              </motion.button>
            );
          })}
        </div>
      )}

      {type === "numerical" && (
        <div className="mt-5 max-w-xs">
          <input
            inputMode="decimal"
            placeholder="Enter your answer"
            className={inputCls}
            disabled={disabled}
            value={typeof response === "string" ? response : ""}
            onChange={(e) => onChange?.(e.target.value.replace(/[^0-9.\-]/g, ""))}
          />
          {reveal && <p className="mt-2 text-sm text-muted">Correct answer: {formatAnswer(answer ?? null)}</p>}
        </div>
      )}

      {type === "subjective" && (
        <p className="mt-5 rounded-xl bg-sunken px-4 py-3 text-sm text-muted">
          Subjective question. Work it out on paper; it is not auto-graded.
        </p>
      )}
    </div>
  );
}
