"use client";

import { ChevronRight, History } from "lucide-react";
import Link from "next/link";

import { Badge, Button, Card, EmptyState, PageHeader, Reveal, Skeleton } from "@/components/ui";
import type { AttemptSummary } from "@/lib/api";
import { formatDate, useApi } from "@/lib/hooks";

export default function HistoryPage() {
  const { data, loading } = useApi<AttemptSummary[]>("/api/attempts");

  return (
    <>
      <PageHeader title="Test history" subtitle="Every attempt, with a link to its full analysis." />
      {loading ? (
        <Skeleton className="h-72" />
      ) : data?.length ? (
        <Reveal>
          <Card className="divide-y divide-line">
            {data.map((a) => {
              const pct = a.max_score ? Math.round((100 * (a.score ?? 0)) / a.max_score) : 0;
              const href = a.status === "submitted" ? `/results/${a.id}` : `/attempt/${a.id}`;
              return (
                <Link key={a.id} href={href} className="flex items-center gap-4 px-5 py-4 transition hover:bg-sunken">
                  <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-soft text-sm font-semibold text-brand">
                    {a.status === "submitted" ? `${pct}%` : "…"}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{a.test_title}</p>
                    <p className="text-xs text-subtle">{formatDate(a.submitted_at ?? a.started_at)}</p>
                  </div>
                  {a.status === "submitted" ? (
                    <div className="hidden text-right sm:block">
                      <p className="text-sm font-semibold tabular-nums">
                        {a.score} / {a.max_score}
                      </p>
                      <p className="text-xs text-subtle">{a.accuracy ?? 0}% accuracy</p>
                    </div>
                  ) : (
                    <Badge tone="brand">In progress</Badge>
                  )}
                  <ChevronRight className="h-4 w-4 text-subtle" />
                </Link>
              );
            })}
          </Card>
        </Reveal>
      ) : (
        <EmptyState icon={<History className="h-5 w-5" />} title="No attempts yet" action={<Button href="/tests">Browse tests</Button>} />
      )}
    </>
  );
}
