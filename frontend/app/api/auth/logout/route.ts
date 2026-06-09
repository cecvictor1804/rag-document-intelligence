// Sign out: clear the session cookie and return to the sign-in page. POST-only
// (the user menu submits a form) so a stray link can't log anyone out.

import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE } from "@/lib/auth/config";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const res = NextResponse.redirect(new URL("/sign-in", request.url), { status: 303 });
  res.cookies.delete(SESSION_COOKIE);
  return res;
}
