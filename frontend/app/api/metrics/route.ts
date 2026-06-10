// Proxies POST /api/metrics to the FastAPI backend's deterministic /metrics
// endpoint (figure/ratio + cell-level provenance; no LLM in the path),
// attaching the signed-in user's Bearer token when auth is enabled.

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

  try {
    const upstream = await fetch(`${BACKEND_URL}/metrics`, { method: "POST", headers, body });
    const text = await upstream.text();
    const res = new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
    if (auth.refreshedCookie) {
      res.cookies.set(SESSION_COOKIE, auth.refreshedCookie, sessionCookieOptions());
    }
    return res;
  } catch {
    return Response.json({ error: "Cannot reach the backend." }, { status: 502 });
  }
}
