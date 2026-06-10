// Proxies GET /api/review to the backend's review queue (open reconciliation
// issues — extractions a human should look at), with the auth bearer attached.

import { NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/auth/config";
import { authorizeBackendCall } from "@/lib/auth/bearer";
import { sessionCookieOptions } from "@/lib/auth/session";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  const auth = await authorizeBackendCall();
  if (!auth.ok) {
    return Response.json({ error: auth.error }, { status: auth.status });
  }

  const headers: Record<string, string> = {};
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`;

  try {
    const upstream = await fetch(`${BACKEND_URL}/review`, { headers });
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
