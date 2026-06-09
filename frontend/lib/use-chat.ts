"use client";

import { useCallback, useRef, useState } from "react";

import { parseSSEStream } from "./sse";
import type { ChatMessage, Citation, MetaData } from "./types";

let counter = 0;
const nextId = () => `m${++counter}`;

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const patch = useCallback((id: string, fn: (m: ChatMessage) => ChatMessage) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? fn(m) : m)));
  }, []);

  const send = useCallback(
    async (text: string) => {
      const query = text.trim();
      if (!query || isStreaming) return;

      // Prior completed turns become the conversation history.
      const history = messages
        .filter((m) => !m.error && !m.pending && m.content)
        .map((m) => ({ role: m.role, content: m.content }));

      const userMsg: ChatMessage = { id: nextId(), role: "user", content: query };
      const asstId = nextId();
      setMessages((prev) => [
        ...prev,
        userMsg,
        { id: asstId, role: "assistant", content: "", pending: true },
      ]);
      setIsStreaming(true);

      const ctrl = new AbortController();
      abortRef.current = ctrl;

      try {
        const res = await fetch("/api/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query, history }),
          signal: ctrl.signal,
        });
        if (!res.ok || !res.body) {
          let detail = `Request failed (${res.status})`;
          try {
            const j = await res.json();
            if (j?.error) detail = j.error;
          } catch {
            /* ignore */
          }
          throw new Error(detail);
        }

        for await (const ev of parseSSEStream(res.body)) {
          if (ev.type === "token") {
            const tok = ev.data as string;
            patch(asstId, (m) => ({ ...m, content: m.content + tok, pending: false }));
          } else if (ev.type === "citations") {
            patch(asstId, (m) => ({ ...m, citations: ev.data as Citation[] }));
          } else if (ev.type === "meta") {
            patch(asstId, (m) => ({ ...m, meta: ev.data as MetaData }));
          } else if (ev.type === "done") {
            patch(asstId, (m) => ({ ...m, pending: false }));
          }
        }
      } catch (e) {
        if ((e as Error)?.name === "AbortError") {
          patch(asstId, (m) => ({ ...m, pending: false }));
        } else {
          const msg = e instanceof Error ? e.message : "Something went wrong";
          patch(asstId, (m) => ({
            ...m,
            pending: false,
            error: true,
            content: m.content || msg,
          }));
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [messages, isStreaming, patch],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  return { messages, isStreaming, send, stop };
}
