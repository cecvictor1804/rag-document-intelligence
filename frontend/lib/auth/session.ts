// The user session: an encrypted (JWE) HttpOnly cookie. It holds the Google ID
// token we forward to the backend plus the refresh token used to keep it fresh,
// so it must be encrypted at rest, not merely signed.

import { EncryptJWT, jwtDecrypt } from "jose";
import { cookies } from "next/headers";

import { SESSION_COOKIE, authSecret } from "./config";

export type Session = {
  sub: string;
  email: string;
  name: string;
  picture: string;
  hd: string;
  idToken: string;
  refreshToken?: string;
  idTokenExp: number; // epoch seconds
};

// 32-byte key for A256GCM, derived from AUTH_SECRET so any secret string works.
async function key(): Promise<Uint8Array> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(authSecret()));
  return new Uint8Array(digest);
}

export async function encodeSession(session: Session): Promise<string> {
  return new EncryptJWT({ ...session })
    .setProtectedHeader({ alg: "dir", enc: "A256GCM" })
    .setIssuedAt()
    .setExpirationTime("7d")
    .encrypt(await key());
}

export async function decodeSession(token: string): Promise<Session | null> {
  try {
    const { payload } = await jwtDecrypt(token, await key());
    return payload as unknown as Session;
  } catch {
    return null;
  }
}

/** Read + decrypt the current session (server components / route handlers). */
export async function getSession(): Promise<Session | null> {
  const jar = await cookies();
  const raw = jar.get(SESSION_COOKIE)?.value;
  return raw ? decodeSession(raw) : null;
}

export function sessionCookieOptions(maxAgeSeconds = 7 * 24 * 60 * 60) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: maxAgeSeconds,
  };
}
