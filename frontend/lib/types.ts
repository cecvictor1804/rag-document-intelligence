// Mirrors the backend AnswerEvent / Citation shapes (backend/app/core/models.py
// + the SSE serialization in backend/app/api/routes.py).

export type Citation = {
  n: number;
  doc_id: string;
  title: string;
  section: string | null;
  source_url: string;
  snippet: string;
};

export type MetaData = {
  model: string | null;
  effort?: string;
  reason?: string;
  top_score?: number;
  n_results?: number;
};

// One planner-resolved figure embedded in a chat answer (backend
// generation/service.py _metric_payload — FactProvenance-shaped inputs).
export type MetricEventData = {
  metric: string;
  value: string;
  unit: string;
  currency: string | null;
  period: string;
  formula: string;
  inputs: FactProvenance[];
};

export type SeriesEventData = {
  metric: string;
  unit: string;
  currency: string | null;
  points: { period: string; value: number }[];
};

export type SSEEvent =
  | { type: "meta"; data: MetaData }
  | { type: "token"; data: string }
  | { type: "citations"; data: Citation[] }
  | { type: "metrics"; data: MetricEventData[] }
  | { type: "series"; data: SeriesEventData }
  | { type: "verification"; data: { unverified: string[] } }
  | { type: "done"; data: { model: string | null; usage: Record<string, number> } }
  | { type: "error"; data: unknown };

// Mirrors backend/app/api/schemas.py MetricResponse / FactProvenance.
// Decimal values arrive as strings to preserve exactness.
export type FactProvenance = {
  line_item: string | null;
  line_item_as_reported: string;
  value: string;
  value_as_reported: string;
  scale: number;
  currency: string;
  unit: string;
  basis: string;
  segment: string | null;
  period: string;
  doc_id: string;
  page: number | null;
  table_index: number | null;
  row: number | null;
  col: number | null;
};

export type MetricResponse = {
  metric: string;
  value: string;
  unit: string;
  currency: string | null;
  period: string;
  formula: string;
  inputs: FactProvenance[];
  converted: {
    currency: string;
    value: string;
    rate: string;
    rate_date: string | null;
  } | null;
  non_gaap_alternative: {
    basis: string;
    value: string;
    label: string;
  } | null;
  disclaimer: string;
};

export type ReviewIssue = {
  id: number;
  doc_id: string;
  entity_id: string;
  check: string;
  detail: string;
  expected: string | null;
  actual: string | null;
  created_at: string;
};

export type Role = "user" | "assistant";

export type ChatMessage = {
  id: string;
  role: Role;
  content: string;
  citations?: Citation[];
  meta?: MetaData;
  metrics?: MetricEventData[];
  series?: SeriesEventData[];
  unverified?: string[];
  pending?: boolean;
  error?: boolean;
};
