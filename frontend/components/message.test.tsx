import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Message } from "./message";
import type { ChatMessage } from "@/lib/types";

const assistant: ChatMessage = {
  id: "1",
  role: "assistant",
  content: "Meals are capped at $75/day [1].",
  citations: [
    {
      n: 1,
      doc_id: "expense_policy.txt",
      title: "Expenses",
      section: "Meals",
      source_url: "",
      snippet: "Meal cap is $75/day.",
    },
  ],
  meta: { model: "claude-haiku-4-5" },
};

describe("Message", () => {
  it("renders assistant content, sources, and the routed-model badge", () => {
    render(<Message message={assistant} />);
    expect(screen.getByText(/Meals are capped/)).toBeInTheDocument();
    expect(screen.getByText("Sources")).toBeInTheDocument();
    expect(screen.getByText("Expenses")).toBeInTheDocument();
    expect(screen.getByText("Haiku")).toBeInTheDocument();
  });

  it("renders a user message verbatim (no citation parsing)", () => {
    render(<Message message={{ id: "2", role: "user", content: "Why [1]?" }} />);
    expect(screen.getByText("Why [1]?")).toBeInTheDocument();
  });

  it("renders verified metric cards with provenance and a verification flag", () => {
    const message: ChatMessage = {
      id: "3",
      role: "assistant",
      content: "Gross margin was 46.22%.",
      metrics: [
        {
          metric: "gross_margin",
          value: "46.222",
          unit: "percent",
          currency: null,
          period: "Q3 FY2024",
          formula: "gross_profit / revenue",
          inputs: [
            {
              line_item: "revenue",
              line_item_as_reported: "Net sales",
              value: "94930000000",
              value_as_reported: "94930",
              scale: 1_000_000,
              currency: "USD",
              unit: "currency",
              basis: "gaap",
              segment: null,
              period: "Q3 FY2024",
              doc_id: "acme-10q.html",
              page: 4,
              table_index: 0,
              row: 1,
              col: 1,
            },
          ],
        },
      ],
      unverified: ["12.5%"],
      meta: { model: "claude-haiku-4-5" },
    };
    render(<Message message={message} />);

    expect(screen.getByText("46.22%")).toBeInTheDocument();
    expect(screen.getByText(/gross margin · Q3 FY2024/)).toBeInTheDocument();
    expect(screen.getByText(/1 source cell/)).toBeInTheDocument();
    expect(
      screen.getByText(/1 number could not be verified/),
    ).toBeInTheDocument();
  });
});
