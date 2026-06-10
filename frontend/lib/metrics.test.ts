import { describe, expect, it } from "vitest";

import { formatAsReported, formatMetricValue } from "./metrics";

describe("formatMetricValue", () => {
  it("formats percents and ratios", () => {
    expect(formatMetricValue("46.222", "percent")).toBe("46.22%");
    expect(formatMetricValue("6.069", "percent")).toBe("6.06%");
    expect(formatMetricValue("0.867", "ratio")).toBe("0.86");
    expect(formatMetricValue("5.400", "ratio")).toBe("5.4");
  });

  it("compacts large currency values without float drift", () => {
    expect(formatMetricValue("94930000000", "currency", "USD")).toBe("$94.93B");
    expect(formatMetricValue("-1234000000", "currency", "USD")).toBe("-$1.23B");
    expect(formatMetricValue("99584000000", "currency", "USD")).toBe("$99.58B");
    expect(formatMetricValue("412000000", "currency", "USD")).toBe("$412M");
  });

  it("keeps small per-share values exact", () => {
    expect(formatMetricValue("0.97", "per_share", "USD")).toBe("$0.97");
    expect(formatMetricValue("1.64", "per_share", "USD")).toBe("$1.64");
  });
});

describe("formatAsReported", () => {
  it("annotates the printed scale", () => {
    expect(formatAsReported("94930", 1_000_000)).toBe("94,930 ×10⁶");
    expect(formatAsReported("1234", 1_000)).toBe("1,234 ×10³");
    expect(formatAsReported("0.97", 1)).toBe("0.97");
  });
});
