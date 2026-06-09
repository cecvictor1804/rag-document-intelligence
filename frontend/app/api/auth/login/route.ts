// Starts the Google sign-in flow: generate PKCE verifier + CSRF state + nonce,
// stash them in short-lived HttpOnly cookies, and redirect to Google's consent
// screen. The matching /callback completes the exchange.

import { NextResponse } from "next/server";

import {
  NONCE_COOKIE,
  STATE_COOKIE,
  VERIFIER_COOKIE,
  authEnabled,
} from "@/lib/auth/config";
import { buildAuthUrl, codeChallenge, randomToken } from "@/lib/auth/google";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  if (!authEnabled) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  const state = randomToken();
  const nonce = randomToken();
  const verifier = randomToken(48);
  const challenge = await codeChallenge(verifier);

  const res = NextResponse.redirect(buildAuthUrl({ state, nonce, challenge }));
  const opts = {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: 600, // 10 minutes to complete the round-trip
  };
  res.cookies.set(STATE_COOKIE, state, opts);
  res.cookies.set(NONCE_COOKIE, nonce, opts);
  res.cookies.set(VERIFIER_COOKIE, verifier, opts);
  return res;
}
