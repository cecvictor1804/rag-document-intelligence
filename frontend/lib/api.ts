export async function sendFeedback(input: {
  query: string;
  answer: string;
  rating: 1 | -1;
  chunk_ids?: number[];
}): Promise<{ id: number }> {
  const res = await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(`Feedback failed (${res.status})`);
  return res.json();
}
