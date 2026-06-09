// Proxies POST /api/query to the FastAPI backend's /query and streams the SSE
// response straight back to the browser. The browser never talks to the backend
// directly (no CORS). When auth is enabled this attaches the signed-in user's
// Google ID token as a Bearer credential (refreshing it if it's about to expire).

import { NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/auth/config";
import { authorizeBackendCall } from "@/lib/auth/bearer";
import { sessionCookieOptions } from "@/lib/auth/session";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  const auth = await authorizeBackendCall();
  if (!auth.ok) {
    return Response.json({ error: auth.error }, { status: auth.status });
  }

  const body = await request.text();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`;

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}/query`, { method: "POST", headers, body });
  } catch {
    return Response.json(
      { error: "Cannot reach the backend. Is it running on " + BACKEND_URL + "?" },
      { status: 502 },
    );
  }

  if (!upstream.ok || !upstream.body) {
    return Response.json({ error: `Backend returned ${upstream.status}` }, { status: 502 });
  }

  const res = new NextResponse(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      // Disable proxy buffering so chunks arrive progressively.
      "X-Accel-Buffering": "no",
    },
  });
  if (auth.refreshedCookie) {
    res.cookies.set(SESSION_COOKIE, auth.refreshedCookie, sessionCookieOptions());
  }
  return res;
}
