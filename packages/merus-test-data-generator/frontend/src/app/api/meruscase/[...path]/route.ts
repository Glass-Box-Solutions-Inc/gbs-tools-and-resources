import { NextRequest } from "next/server";

const BACKEND = "http://localhost:5520";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const backendPath = path.join("/");

  let body: string | undefined;
  try {
    const json = await request.json();
    body = JSON.stringify(json);
  } catch {
    // No body
  }

  const res = await fetch(`${BACKEND}/api/meruscase/${backendPath}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });

  const data = await res.text();
  return new Response(data, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
  });
}

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const backendPath = path.join("/");

  const res = await fetch(`${BACKEND}/api/meruscase/${backendPath}`, {
    cache: "no-store",
    headers: { Accept: "text/event-stream" },
  });

  const contentType = res.headers.get("Content-Type") || "application/json";

  if (contentType.includes("text/event-stream")) {
    return new Response(res.body, {
      status: res.status,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  }

  const data = await res.text();
  return new Response(data, {
    status: res.status,
    headers: { "Content-Type": contentType },
  });
}
