// Decides what (if anything) to attach to a backend call on behalf of the user,
// refreshing the Google ID token when it's about to expire. Shared by the
// /api/query and /api/feedback proxy routes.

import { authEnabled } from "./config";
import { refreshIdToken, verifyGoogleIdToken } from "./google";
import { encodeSession, getSession } from "./session";

export type Authorized =
  | { ok: true; token: string | null; refreshedCookie?: string }
  | { ok: false; status: number; error: string };

const REFRESH_SKEW_SECONDS = 60;

/** True when the ID token has expired or is within the refresh skew window. */
export function needsRefresh(idTokenExp: number, nowSeconds: number): boolean {
  return idTokenExp - nowSeconds < REFRESH_SKEW_SECONDS;
}

export async function authorizeBackendCall(): Promise<Authorized> {
  // Auth off (local dev): forward with no Authorization header, as in Phase 3a.
  if (!authEnabled) return { ok: true, token: null };

  const session = await getSession();
  if (!session) return { ok: false, status: 401, error: "Not authenticated" };

  const nowSeconds = Math.floor(Date.now() / 1000);
  if (!needsRefresh(session.idTokenExp, nowSeconds)) {
    return { ok: true, token: session.idToken };
  }

  // Token is stale — refresh it transparently and re-issue the session cookie.
  if (!session.refreshToken) return { ok: false, status: 401, error: "Session expired" };
  try {
    const tokens = await refreshIdToken(session.refreshToken);
    await verifyGoogleIdToken(tokens.id_token);
    const refreshed = {
      ...session,
      idToken: tokens.id_token,
      idTokenExp: nowSeconds + tokens.expires_in,
    };
    return {
      ok: true,
      token: refreshed.idToken,
      refreshedCookie: await encodeSession(refreshed),
    };
  } catch {
    return { ok: false, status: 401, error: "Session refresh failed" };
  }
}
