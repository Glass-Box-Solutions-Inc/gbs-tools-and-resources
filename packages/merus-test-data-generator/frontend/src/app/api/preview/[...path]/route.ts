import { NextRequest } from "next/server";

const BACKEND = "http://localhost:5520";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const backendPath = path.join("/");
  const res = await fetch(`${BACKEND}/api/preview/${backendPath}`, {
    cache: "no-store",
  });

  const contentType = res.headers.get("Content-Type") || "application/json";

  // For PDF files, stream the response body
  if (contentType.includes("application/pdf")) {
    return new Response(res.body, {
      status: res.status,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition":
          res.headers.get("Content-Disposition") || "inline",
      },
    });
  }

  const data = await res.text();
  return new Response(data, {
    status: res.status,
    headers: { "Content-Type": contentType },
  });
}
