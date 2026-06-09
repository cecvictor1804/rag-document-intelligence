import { describe, expect, it } from "vitest";

import { parseFrame, parseSSEStream } from "./sse";
import type { SSEEvent } from "./types";

function streamFrom(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(c) {
      for (const ch of chunks) c.enqueue(enc.encode(ch));
      c.close();
    },
  });
}

describe("parseFrame", () => {
  it("parses a token frame (JSON-encoded string)", () => {
    expect(parseFrame('event: token\ndata: "hello"')).toEqual({
      type: "token",
      data: "hello",
    });
  });

  it("parses a citations array", () => {
    expect(parseFrame('event: citations\ndata: [{"n":1,"doc_id":"a"}]')).toEqual({
      type: "citations",
      data: [{ n: 1, doc_id: "a" }],
    });
  });

  it("returns null when there is no data line", () => {
    expect(parseFrame("event: ping")).toBeNull();
  });
});

describe("parseSSEStream", () => {
  it("yields events across chunk splits and handles CRLF", async () => {
    const stream = streamFrom([
      'event: meta\r\ndata: {"model":"claude-haiku-4-5"}\r\n\r\n',
      "event: tok",
      'en\ndata: "Hi"\n\n',
      'event: done\ndata: {"model":"x","usage":{}}\n\n',
    ]);

    const out: SSEEvent[] = [];
    for await (const ev of parseSSEStream(stream)) out.push(ev);

    expect(out.map((e) => e.type)).toEqual(["meta", "token", "done"]);
    expect(out[1]).toEqual({ type: "token", data: "Hi" });
  });
});
