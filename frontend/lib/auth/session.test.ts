// @vitest-environment node
import { describe, expect, it } from "vitest";

import { decodeSession, encodeSession, type Session } from "./session";

const SAMPLE: Session = {
  sub: "1234567890",
  email: "alice@example.com",
  name: "Alice",
  picture: "https://example.com/a.png",
  hd: "example.com",
  idToken: "header.payload.signature",
  refreshToken: "refresh-xyz",
  idTokenExp: 1_900_000_000,
};

describe("session cookie", () => {
  it("round-trips an encrypted session", async () => {
    const jwe = await encodeSession(SAMPLE);
    // It's a compact JWE (5 dot-separated segments), not plaintext.
    expect(jwe.split(".")).toHaveLength(5);
    expect(jwe).not.toContain("refresh-xyz");

    const decoded = await decodeSession(jwe);
    expect(decoded).toMatchObject(SAMPLE);
  });

  it("returns null for a tampered or bogus token", async () => {
    expect(await decodeSession("not-a-jwe")).toBeNull();
    const jwe = await encodeSession(SAMPLE);
    expect(await decodeSession(jwe.slice(0, -4) + "AAAA")).toBeNull();
  });
});
