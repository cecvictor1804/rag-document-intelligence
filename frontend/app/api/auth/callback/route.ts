// Completes Google sign-in: validate state, exchange the code for tokens, verify
// the ID token (signature + domain policy), then establish the session cookie.

import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

import {
  NONCE_COOKIE,
  SESSION_COOKIE,
  STATE_COOKIE,
  VERIFIER_COOKIE,
  authEnabled,
} from "@/lib/auth/config";
import { exchangeCode, verifyGoogleIdToken } from "@/lib/auth/google";
import { encodeSession, sessionCookieOptions, type Session } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const failTo = (reason: string) =>
    NextResponse.redirect(new URL(`/sign-in?error=${reason}`, request.url));

  if (!authEnabled) return NextResponse.redirect(new URL("/", request.url));

  const params = request.nextUrl.searchParams;
  const code = params.get("code");
  const state = params.get("state");

  const jar = await cookies();
  const expectedState = jar.get(STATE_COOKIE)?.value;
  const nonce = jar.get(NONCE_COOKIE)?.value;
  const verifier = jar.get(VERIFIER_COOKIE)?.value;

  if (!code || !state || !expectedState || state !== expectedState || !verifier) {
    return failTo("invalid_state");
  }

  try {
    const tokens = await exchangeCode(code, verifier);
    const claims = await verifyGoogleIdToken(tokens.id_token, nonce);

    const session: Session = {
      sub: claims.sub,
      email: claims.email,
      name: claims.name ?? "",
      picture: claims.picture ?? "",
      hd: claims.hd ?? "",
      idToken: tokens.id_token,
      refreshToken: tokens.refresh_token,
      idTokenExp: Math.floor(Date.now() / 1000) + tokens.expires_in,
    };

    const res = NextResponse.redirect(new URL("/", request.url));
    res.cookies.set(SESSION_COOKIE, await encodeSession(session), sessionCookieOptions());
    for (const name of [STATE_COOKIE, NONCE_COOKIE, VERIFIER_COOKIE]) {
      res.cookies.delete(name);
    }
    return res;
  } catch {
    return failTo("auth_failed");
  }
}
