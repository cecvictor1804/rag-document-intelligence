"use client";

// Verified-figure cards rendered inside an assistant message: the
// deterministically computed value plus an expandable source-cell line —
// the same provenance the metrics panel shows, in compact form.

import { ChevronDown } from "lucide-react";
import * as React from "react";

import { formatAsReported, formatMetricValue } from "@/lib/metrics";
import type { MetricEventData } from "@/lib/types";
import { cn } from "@/lib/utils";

function Card({ metric }: { metric: MetricEventData }) {
  const [open, setOpen] = React.useState(false);

  return (
    <div className="rounded-xl border bg-card/80 px-3 py-2 shadow-sm">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {metric.metric.replaceAll("_", " ")} · {metric.period}
      </p>
      <p className="text-lg font-semibold tabular-nums tracking-tight">
        {formatMetricValue(metric.value, metric.unit, metric.currency)}
      </p>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mt-0.5 flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
        aria-expanded={open}
      >
        <ChevronDown className={cn("size-3 transition-transform", open && "rotate-180")} />
        {metric.inputs.length} source cell{metric.inputs.length === 1 ? "" : "s"}
      </button>
      {open && (
        <ul className="mt-1 space-y-1 border-t pt-1.5">
          {metric.inputs.map((f, i) => (
            <li key={i} className="text-[11px] leading-snug text-muted-foreground">
              <span className="font-medium text-foreground">{f.line_item_as_reported}</span>{" "}
              {formatAsReported(f.value_as_reported, f.scale)} {f.currency} — {f.doc_id}
              {f.page != null && ` · p.${f.page}`}
              {f.table_index != null && ` · table ${f.table_index}`}
              {f.row != null && f.col != null && ` · r${f.row},c${f.col}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function MetricCards({ metrics }: { metrics: MetricEventData[] }) {
  return (
    <div className="mb-2 flex flex-wrap gap-2">
      {metrics.map((m, i) => (
        <Card key={`${m.metric}-${m.period}-${i}`} metric={m} />
      ))}
    </div>
  );
}
