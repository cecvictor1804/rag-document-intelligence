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
