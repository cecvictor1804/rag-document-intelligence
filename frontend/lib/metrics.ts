// Metric catalog + presentation helpers for the metrics panel. The catalog
// mirrors the backend registry (chart.py canonical items + metrics.py ratios);
// values are Decimal strings from the API and formatted without float drift
// where it matters.

import type { MetricResponse } from "./types";

export type MetricOption = { value: string; label: string };
export type MetricGroup = { label: string; options: MetricOption[] };

export const METRIC_GROUPS: MetricGroup[] = [
  {
    label: "Ratios & margins (computed)",
    options: [
      { value: "gross_margin", label: "Gross margin" },
      { value: "operating_margin", label: "Operating margin" },
      { value: "net_margin", label: "Net margin" },
      { value: "current_ratio", label: "Current ratio" },
      { value: "debt_to_equity", label: "Debt to equity" },
    ],
  },
  {
    label: "Growth (computed)",
    options: [
      { value: "revenue_yoy", label: "Revenue YoY" },
      { value: "net_income_yoy", label: "Net income YoY" },
      { value: "operating_income_yoy", label: "Operating income YoY" },
    ],
  },
  {
    label: "Reported figures",
    options: [
      { value: "revenue", label: "Revenue" },
      { value: "gross_profit", label: "Gross profit" },
      { value: "operating_income", label: "Operating income" },
      { value: "net_income", label: "Net income" },
      { value: "eps_diluted", label: "EPS (diluted)" },
      { value: "total_assets", label: "Total assets" },
      { value: "total_liabilities", label: "Total liabilities" },
      { value: "total_equity", label: "Total equity" },
      { value: "cash_and_equivalents", label: "Cash & equivalents" },
      { value: "operating_cash_flow", label: "Operating cash flow" },
    ],
  },
];

const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: "$", EUR: "€", GBP: "£", JPY: "¥",
};

/** Format a Decimal-string metric value for display.
 * percent -> "46.22%", ratio -> "0.87", currency -> "$94.93B" (compact). */
export function formatMetricValue(value: string, unit: string, currency?: string | null): string {
  if (unit === "percent") return `${trimDecimal(value, 2)}%`;
  if (unit === "ratio") return trimDecimal(value, 2);

  const symbol = currency ? (CURRENCY_SYMBOLS[currency] ?? `${currency} `) : "";
  const negative = value.startsWith("-");
  const digits = (negative ? value.slice(1) : value).split(".")[0];

  if (unit === "currency" && digits.length > 4) {
    const scaled = compactNumber(value);
    return `${negative ? "-" : ""}${symbol}${scaled}`;
  }
  return `${negative ? "-" : ""}${symbol}${trimDecimal(negative ? value.slice(1) : value, 2)}`;
}

/** "94930000000" -> "94.93B" without going through float for the magnitude. */
function compactNumber(value: string): string {
  const negative = value.startsWith("-");
  const [whole] = (negative ? value.slice(1) : value).split(".");
  const units: Array<[number, string]> = [[13, "T"], [10, "B"], [7, "M"], [4, "K"]];
  for (const [minDigits, suffix] of units) {
    if (whole.length >= minDigits) {
      const head = whole.length - (minDigits - 1);
      const lead = whole.slice(0, head);
      const frac = whole.slice(head, head + 2);
      return `${lead}${frac ? "." + frac : ""}${suffix}`.replace(/\.00([A-Z])$/, "$1");
    }
  }
  return Number(whole).toLocaleString();
}

function trimDecimal(value: string, places: number): string {
  const [whole, frac] = value.split(".");
  const grouped = Number(whole).toLocaleString();
  if (!frac || places === 0) return grouped;
  const cut = frac.slice(0, places).replace(/0+$/, "");
  return cut ? `${grouped}.${cut}` : grouped;
}

/** Format an as-reported value with its scale for provenance rows:
 * ("94930", 1000000) -> "94,930 ×10⁶". */
export function formatAsReported(value: string, scale: number): string {
  const base = trimDecimal(value, 2);
  if (scale === 1_000) return `${base} ×10³`;
  if (scale === 1_000_000) return `${base} ×10⁶`;
  if (scale === 1_000_000_000) return `${base} ×10⁹`;
  return base;
}

export async function fetchReview(): Promise<import("./types").ReviewIssue[]> {
  const res = await fetch("/api/review");
  if (!res.ok) throw new Error(`Review fetch failed (${res.status})`);
  const body = (await res.json()) as { issues: import("./types").ReviewIssue[] };
  return body.issues;
}

export async function fetchMetric(input: {
  entity: string;
  metric: string;
  fiscal_year: number;
  fiscal_quarter: number | null;
  currency?: string | null;
}): Promise<MetricResponse> {
  const res = await fetch("/api/metrics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const j = await res.json();
      detail = j?.detail ?? j?.error ?? detail;
    } catch {
      /* keep default */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<MetricResponse>;
}
