// @vitest-environment node
import { describe, expect, it } from "vitest";

import { needsRefresh } from "./bearer";

describe("needsRefresh", () => {
  const now = 1_900_000_000;

  it("is false when the token has comfortable life left", () => {
    expect(needsRefresh(now + 300, now)).toBe(false);
  });

  it("is true within the 60s skew window", () => {
    expect(needsRefresh(now + 30, now)).toBe(true);
  });

  it("is true once expired", () => {
    expect(needsRefresh(now - 10, now)).toBe(true);
  });
});
