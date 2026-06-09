// Next.js 16 Proxy (the renamed Middleware). Optimistic auth gate: if a request
// for a page route has no session cookie, redirect to /sign-in. This is a
// cookie-presence check only (no decryption/network, per the proxy guidance) —
// the real verification happens at the backend on every /query. No-op when auth
// is disabled, so local dev behaves exactly like Phase 3a.

import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE, authEnabled } from "@/lib/auth/config";

const PUBLIC_PATHS = ["/sign-in"];

export function proxy(request: NextRequest) {
  if (!authEnabled) return NextResponse.next();

  const { pathname } = request.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return NextResponse.next();
  }

  if (!request.cookies.has(SESSION_COOKIE)) {
    const url = request.nextUrl.clone();
    url.pathname = "/sign-in";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

// Run on everything except API routes (guarded at the route level), Next
// internals, and static assets.
export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.[\\w]+$).*)"],
};
