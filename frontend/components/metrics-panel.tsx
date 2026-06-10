"use client";

// Deterministic metrics panel: ask for a figure/ratio, get the exact value
// with cell-level provenance (doc, page, table, row, col) — no LLM involved.
// Self-contained launcher + slide-over so the (server) page can mount it.

import { BarChart3, Loader2, X } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  METRIC_GROUPS,
  fetchMetric,
  fetchReview,
  formatAsReported,
  formatMetricValue,
} from "@/lib/metrics";
import type { MetricResponse, ReviewIssue } from "@/lib/types";
import { cn } from "@/lib/utils";

const FIELD =
  "w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60";

export function MetricsPanel() {
  const [open, setOpen] = React.useState(false);
  const [entity, setEntity] = React.useState("ACME");
  const [metric, setMetric] = React.useState("gross_margin");
  const [year, setYear] = React.useState(2024);
  const [quarter, setQuarter] = React.useState<string>("3");
  const [currency, setCurrency] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<MetricResponse | null>(null);
  const [issues, setIssues] = React.useState<ReviewIssue[] | null>(null);

  // Data quality: open reconciliation issues, fetched when the panel opens.
  React.useEffect(() => {
    if (!open) return;
    let cancelled = false;
    fetchReview()
      .then((list) => !cancelled && setIssues(list))
      .catch(() => !cancelled && setIssues(null));
    return () => {
      cancelled = true;
    };
  }, [open]);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await fetchMetric({
          entity: entity.trim(),
          metric,
          fiscal_year: year,
          fiscal_quarter: quarter === "FY" ? null : Number(quarter),
          currency: currency.trim() ? currency.trim().toUpperCase() : null,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Open metrics panel"
        onClick={() => setOpen(true)}
      >
        <BarChart3 className="size-4" />
      </Button>

      {/* Backdrop */}
      <div
        aria-hidden
        onClick={() => setOpen(false)}
        className={cn(
          "fixed inset-0 z-30 bg-black/30 backdrop-blur-[2px] transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      />

      {/* Slide-over */}
      <aside
        role="dialog"
        aria-label="Financial metrics"
        className={cn(
          "fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l",
          "bg-background/95 shadow-xl backdrop-blur-md transition-transform duration-200",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <BarChart3 className="size-4 text-primary" />
            <span className="font-semibold tracking-tight">Metrics</span>
            <span className="text-xs text-muted-foreground">deterministic · cell-cited</span>
          </div>
          <Button variant="ghost" size="icon" aria-label="Close metrics panel" onClick={() => setOpen(false)}>
            <X className="size-4" />
          </Button>
        </div>

        <form onSubmit={run} className="grid grid-cols-2 gap-3 border-b px-4 py-4">
          <label className="col-span-2 text-sm">
            <span className="mb-1 block text-xs font-medium text-muted-foreground">Entity</span>
            <input
              className={FIELD}
              value={entity}
              onChange={(e) => setEntity(e.target.value)}
              placeholder="Ticker / entity id"
              required
            />
          </label>
          <label className="col-span-2 text-sm">
            <span className="mb-1 block text-xs font-medium text-muted-foreground">Metric</span>
            <select className={FIELD} value={metric} onChange={(e) => setMetric(e.target.value)}>
              {METRIC_GROUPS.map((g) => (
                <optgroup key={g.label} label={g.label}>
                  {g.options.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium text-muted-foreground">Fiscal year</span>
            <input
              type="number"
              className={FIELD}
              value={year}
              min={1990}
              max={2200}
              onChange={(e) => setYear(Number(e.target.value))}
              required
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium text-muted-foreground">Period</span>
            <select className={FIELD} value={quarter} onChange={(e) => setQuarter(e.target.value)}>
              <option value="FY">Full year</option>
              <option value="1">Q1</option>
              <option value="2">Q2</option>
              <option value="3">Q3</option>
              <option value="4">Q4</option>
            </select>
          </label>
          <label className="col-span-2 text-sm">
            <span className="mb-1 block text-xs font-medium text-muted-foreground">
              Convert to currency (optional, e.g. EUR)
            </span>
            <input
              className={FIELD}
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              placeholder="As reported"
              maxLength={3}
            />
          </label>
          <Button type="submit" className="col-span-2" disabled={loading}>
            {loading ? <Loader2 className="size-4 animate-spin" /> : "Get figure"}
          </Button>
        </form>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {error && (
            <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}

          {result && (
            <div className="space-y-4">
              <div className="rounded-xl border bg-card p-4 shadow-sm">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">
                  {result.metric.replaceAll("_", " ")} · {result.period}
                </p>
                <p className="mt-1 text-3xl font-semibold tabular-nums tracking-tight">
                  {formatMetricValue(result.value, result.unit, result.currency)}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">= {result.formula}</p>
                {result.converted && (
                  <p className="mt-1 text-sm tabular-nums text-muted-foreground">
                    ≈ {formatMetricValue(result.converted.value, "currency", result.converted.currency)}
                    <span className="text-xs">
                      {" "}@ {result.converted.rate}
                      {result.converted.rate_date && ` (${result.converted.rate_date})`}
                    </span>
                  </p>
                )}
                {result.non_gaap_alternative && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {result.non_gaap_alternative.basis === "non_gaap" ? "Non-GAAP" : "GAAP"}{" "}
                    counterpart: {result.non_gaap_alternative.label} ={" "}
                    {formatMetricValue(
                      result.non_gaap_alternative.value, result.unit, result.currency,
                    )}
                  </p>
                )}
              </div>

              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Source cells
                </p>
                <ul className="space-y-2">
                  {result.inputs.map((f, i) => (
                    <li key={i} className="rounded-lg border bg-card/60 p-3 text-sm">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="font-medium">{f.line_item_as_reported}</span>
                        <span className="tabular-nums text-muted-foreground">
                          {formatAsReported(f.value_as_reported, f.scale)} {f.currency}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {f.doc_id}
                        {f.page != null && ` · p.${f.page}`}
                        {f.table_index != null && ` · table ${f.table_index}`}
                        {f.row != null && f.col != null && ` · row ${f.row}, col ${f.col}`}
                        {" · "}{f.period}
                        {f.basis !== "gaap" && " · non-GAAP"}
                        {f.segment && ` · ${f.segment}`}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>

              <p className="text-xs text-muted-foreground">{result.disclaimer}</p>
            </div>
          )}

          {!result && !error && (
            <p className="text-sm text-muted-foreground">
              Look up a reported figure or a computed ratio. Every number is
              traced to the exact table cell it came from — ingest a filing
              first with <code className="rounded bg-muted px-1">make ingest-financial</code>.
            </p>
          )}

          {issues && issues.length > 0 && (
            <div className="mt-6 border-t pt-4">
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-amber-600 dark:text-amber-400">
                Data quality — {issues.length} flagged extraction
                {issues.length === 1 ? "" : "s"}
              </p>
              <ul className="space-y-2">
                {issues.map((issue) => (
                  <li
                    key={issue.id}
                    className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs"
                  >
                    <p className="font-medium">
                      {issue.entity_id} · {issue.doc_id}
                    </p>
                    <p className="mt-0.5 text-muted-foreground">
                      {issue.detail}
                      {issue.expected && issue.actual && (
                        <> — expected {issue.expected}, got {issue.actual}</>
                      )}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
