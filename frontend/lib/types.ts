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

export type SSEEvent =
  | { type: "meta"; data: MetaData }
  | { type: "token"; data: string }
  | { type: "citations"; data: Citation[] }
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
  disclaimer: string;
};

export type Role = "user" | "assistant";

export type ChatMessage = {
  id: string;
  role: Role;
  content: string;
  citations?: Citation[];
  meta?: MetaData;
  pending?: boolean;
  error?: boolean;
};
