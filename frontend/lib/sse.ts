import type { SSEEvent } from "./types";

/**
 * Parse a single SSE frame ("event: x\ndata: y") into a typed event.
 * `data` is JSON-parsed (the backend JSON-encodes every payload, including
 * token strings); a frame with no `data:` line returns null.
 */
export function parseFrame(raw: string): SSEEvent | null {
  let event = "message";
  const dataLines: string[] = [];

  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).replace(/^ /, ""));
    }
  }

  if (dataLines.length === 0) return null;

  const dataStr = dataLines.join("\n");
  let data: unknown;
  try {
    data = JSON.parse(dataStr);
  } catch {
    data = dataStr;
  }
  return { type: event, data } as SSEEvent;
}

/**
 * Turn a fetch response body (ReadableStream of bytes) into an async stream of
 * parsed SSE events. Frames are separated by a blank line; partial frames are
 * buffered across chunks. CRLF and LF are both handled.
 */
export async function* parseSSEStream(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<SSEEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r/g, "");

      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const ev = parseFrame(frame);
        if (ev) yield ev;
      }
    }
    const tail = (buffer + decoder.decode()).trim();
    if (tail) {
      const ev = parseFrame(tail);
      if (ev) yield ev;
    }
  } finally {
    reader.releaseLock();
  }
}
