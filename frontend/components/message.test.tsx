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
});
