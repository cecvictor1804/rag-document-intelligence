// Google OIDC: the authorization-code-with-PKCE flow, plus ID-token verification
// against Google's JWKS. Implemented directly (no Auth.js) per the bundled Next
// 16 auth guide — full control and no beta dependency.

import { createRemoteJWKSet, jwtVerify, type JWTPayload } from "jose";

import { googleClientId, googleClientSecret, hostedDomain, redirectUri } from "./config";

const AUTHORIZE_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth";
const TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token";
const ISSUERS = ["https://accounts.google.com", "accounts.google.com"];
const JWKS = createRemoteJWKSet(new URL("https://www.googleapis.com/oauth2/v3/certs"));

export type TokenResponse = {
  id_token: string;
  access_token?: string;
  refresh_token?: string;
  expires_in: number;
};

export type GoogleClaims = JWTPayload & {
  sub: string;
  email: string;
  email_verified?: boolean;
  hd?: string;
  name?: string;
  picture?: string;
  nonce?: string;
};

// ── PKCE / CSRF helpers (Web Crypto) ─────────────────────────────────────────

function base64url(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function randomToken(bytes = 32): string {
  return base64url(crypto.getRandomValues(new Uint8Array(bytes)));
}

export async function codeChallenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64url(new Uint8Array(digest));
}

// ── Flow ─────────────────────────────────────────────────────────────────────

export function buildAuthUrl(opts: { state: string; nonce: string; challenge: string }): string {
  const params = new URLSearchParams({
    client_id: googleClientId(),
    redirect_uri: redirectUri,
    response_type: "code",
    scope: "openid email profile",
    state: opts.state,
    nonce: opts.nonce,
    code_challenge: opts.challenge,
    code_challenge_method: "S256",
    access_type: "offline", // ask for a refresh token
    prompt: "consent",
  });
  if (hostedDomain) params.set("hd", hostedDomain);
  return `${AUTHORIZE_ENDPOINT}?${params.toString()}`;
}

async function postToken(body: URLSearchParams): Promise<TokenResponse> {
  const res = await fetch(TOKEN_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    throw new Error(`Google token endpoint returned ${res.status}`);
  }
  return res.json() as Promise<TokenResponse>;
}

export function exchangeCode(code: string, codeVerifier: string): Promise<TokenResponse> {
  return postToken(
    new URLSearchParams({
      client_id: googleClientId(),
      client_secret: googleClientSecret(),
      code,
      redirect_uri: redirectUri,
      grant_type: "authorization_code",
      code_verifier: codeVerifier,
    }),
  );
}

export function refreshIdToken(refreshToken: string): Promise<TokenResponse> {
  return postToken(
    new URLSearchParams({
      client_id: googleClientId(),
      client_secret: googleClientSecret(),
      refresh_token: refreshToken,
      grant_type: "refresh_token",
    }),
  );
}

/**
 * Verify a Google ID token's signature/issuer/audience, then enforce our
 * domain policy: verified email, allowed `hd`, and (if provided) matching nonce.
 * Throws on any failure.
 */
export async function verifyGoogleIdToken(idToken: string, nonce?: string): Promise<GoogleClaims> {
  const { payload } = await jwtVerify(idToken, JWKS, {
    issuer: ISSUERS,
    audience: googleClientId(),
  });
  const claims = payload as GoogleClaims;

  if (!claims.email_verified) throw new Error("email not verified");
  if (hostedDomain && claims.hd !== hostedDomain) throw new Error("hosted domain not allowed");
  if (nonce && claims.nonce !== nonce) throw new Error("nonce mismatch");

  return claims;
}
