const BACKEND = "http://localhost:5520";

export async function POST(request: Request) {
  const body = await request.json();
  const res = await fetch(`${BACKEND}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.text();
  return new Response(data, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
  });
}

export async function GET(request: Request) {
  // Proxy SSE status stream: GET /api/generate/{runId}/status
  const url = new URL(request.url);
  const runId = url.searchParams.get("runId");
  if (!runId) {
    return new Response(JSON.stringify({ error: "runId required" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const res = await fetch(`${BACKEND}/api/generate/${runId}/status`, {
    headers: { Accept: "text/event-stream" },
  });

  // Transparently proxy the SSE stream
  return new Response(res.body, {
    status: res.status,
    headers: {
      "Content-Type": res.headers.get("Content-Type") || "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
