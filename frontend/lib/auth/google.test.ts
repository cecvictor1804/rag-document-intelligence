// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from "vitest";

import { buildAuthUrl, codeChallenge, randomToken, verifyGoogleIdToken } from "./google";

// Mock jose so verifyGoogleIdToken doesn't hit Google's JWKS.
const jwtVerify = vi.hoisted(() => vi.fn());
vi.mock("jose", () => ({
  createRemoteJWKSet: () => "jwks",
  jwtVerify,
}));

describe("PKCE helpers", () => {
  it("derives the S256 challenge per the RFC 7636 test vector", async () => {
    // Appendix B of RFC 7636.
    const verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    expect(await codeChallenge(verifier)).toBe("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM");
  });

  it("generates distinct URL-safe tokens", () => {
    const a = randomToken();
    const b = randomToken();
    expect(a).not.toBe(b);
    expect(a).toMatch(/^[A-Za-z0-9_-]+$/);
  });
});

describe("buildAuthUrl", () => {
  it("includes PKCE, the hosted domain, and offline access", () => {
    const url = new URL(buildAuthUrl({ state: "st", nonce: "no", challenge: "ch" }));
    const p = url.searchParams;
    expect(p.get("client_id")).toBe("test-client-id");
    expect(p.get("code_challenge")).toBe("ch");
    expect(p.get("code_challenge_method")).toBe("S256");
    expect(p.get("state")).toBe("st");
    expect(p.get("nonce")).toBe("no");
    expect(p.get("hd")).toBe("example.com");
    expect(p.get("access_type")).toBe("offline");
    expect(p.get("redirect_uri")).toBe("http://localhost:3000/api/auth/callback");
  });
});

describe("verifyGoogleIdToken", () => {
  const goodClaims = {
    sub: "1",
    email: "a@example.com",
    email_verified: true,
    hd: "example.com",
    nonce: "n",
  };

  beforeEach(() => jwtVerify.mockReset());

  it("returns claims for a valid, in-domain, verified token", async () => {
    jwtVerify.mockResolvedValue({ payload: goodClaims });
    expect(await verifyGoogleIdToken("tok", "n")).toMatchObject({ email: "a@example.com" });
  });

  it("rejects an unverified email", async () => {
    jwtVerify.mockResolvedValue({ payload: { ...goodClaims, email_verified: false } });
    await expect(verifyGoogleIdToken("tok")).rejects.toThrow(/verified/);
  });

  it("rejects a token from another hosted domain", async () => {
    jwtVerify.mockResolvedValue({ payload: { ...goodClaims, hd: "evil.com" } });
    await expect(verifyGoogleIdToken("tok")).rejects.toThrow(/hosted domain/);
  });

  it("rejects a nonce mismatch", async () => {
    jwtVerify.mockResolvedValue({ payload: goodClaims });
    await expect(verifyGoogleIdToken("tok", "different")).rejects.toThrow(/nonce/);
  });
});
