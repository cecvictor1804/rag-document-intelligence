"use client";

// Multi-period trend chart for a `series` answer event. Recharts line chart,
// themed via the app's CSS variables so it adapts to light/dark.

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatMetricValue } from "@/lib/metrics";
import type { SeriesEventData } from "@/lib/types";

function compactTick(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${(value / 1e12).toFixed(1)}T`;
  if (abs >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
  return String(value);
}

export function TrendChart({ series }: { series: SeriesEventData }) {
  return (
    <div className="mb-2 rounded-xl border bg-card/80 p-3 shadow-sm">
      <p className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">
        {series.metric.replaceAll("_", " ")} · {series.points.length} periods
      </p>
      <div className="h-44 w-full min-w-[16rem]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series.points} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis
              dataKey="period"
              tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
            />
            <YAxis
              tickFormatter={compactTick}
              tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
              tickLine={false}
              axisLine={false}
              width={44}
            />
            <Tooltip
              formatter={(value) =>
                formatMetricValue(String(value), series.unit, series.currency)
              }
              contentStyle={{
                background: "var(--popover)",
                border: "1px solid var(--border)",
                borderRadius: "0.5rem",
                fontSize: "12px",
                color: "var(--popover-foreground)",
              }}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="var(--primary)"
              strokeWidth={2}
              dot={{ r: 3, fill: "var(--primary)" }}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
