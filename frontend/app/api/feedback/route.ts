// Proxies POST /api/feedback to the FastAPI backend's /feedback.

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  const body = await request.text();

  try {
    const upstream = await fetch(`${BACKEND_URL}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return Response.json({ error: "Cannot reach the backend." }, { status: 502 });
  }
}
