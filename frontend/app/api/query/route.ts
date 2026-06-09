// Proxies POST /api/query to the FastAPI backend's /query and streams the SSE
// response straight back to the browser. The browser never talks to the backend
// directly (no CORS), and this is the seam where Phase 3b will attach the
// authenticated user before forwarding.

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  const body = await request.text();

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
  } catch {
    return Response.json(
      { error: "Cannot reach the backend. Is it running on " + BACKEND_URL + "?" },
      { status: 502 },
    );
  }

  if (!upstream.ok || !upstream.body) {
    return Response.json(
      { error: `Backend returned ${upstream.status}` },
      { status: 502 },
    );
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      // Disable proxy buffering so chunks arrive progressively.
      "X-Accel-Buffering": "no",
    },
  });
}
