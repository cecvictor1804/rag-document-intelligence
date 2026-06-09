// Server-only auth configuration, read from the environment. These accessors
// throw if a required secret is missing *when auth is enabled* — so the app
// still boots with AUTH_ENABLED unset (local dev / Phase 3a behavior).

export const SESSION_COOKIE = "__session";

// Short-lived cookies that carry the OAuth flow's CSRF/replay defenses between
// the /login redirect and the /callback.
export const STATE_COOKIE = "oauth_state";
export const NONCE_COOKIE = "oauth_nonce";
export const VERIFIER_COOKIE = "oauth_verifier";

export const authEnabled = process.env.AUTH_ENABLED === "true";
export const appUrl = process.env.APP_URL ?? "http://localhost:3000";
export const redirectUri = `${appUrl}/api/auth/callback`;
export const hostedDomain = process.env.GOOGLE_HOSTED_DOMAIN ?? "";

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required env var ${name} (set it, or unset AUTH_ENABLED)`);
  }
  return value;
}

export const googleClientId = () => required("GOOGLE_CLIENT_ID");
export const googleClientSecret = () => required("GOOGLE_CLIENT_SECRET");
export const authSecret = () => required("AUTH_SECRET");
