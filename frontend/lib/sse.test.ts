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

  it("parses the financial answer frames (metrics, series, verification)", () => {
    const metrics = parseFrame(
      'event: metrics\ndata: [{"metric":"gross_margin","value":"46.222","unit":"percent"}]',
    );
    expect(metrics?.type).toBe("metrics");
    expect((metrics?.data as { metric: string }[])[0].metric).toBe("gross_margin");

    const series = parseFrame(
      'event: series\ndata: {"metric":"revenue","points":[{"period":"Q3 FY2024","value":94930000000}]}',
    );
    expect(series?.type).toBe("series");

    expect(parseFrame('event: verification\ndata: {"unverified":["12.5%"]}')).toEqual({
      type: "verification",
      data: { unverified: ["12.5%"] },
    });
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
