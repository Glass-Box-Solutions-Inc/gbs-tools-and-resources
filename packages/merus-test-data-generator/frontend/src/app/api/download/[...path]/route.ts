import { NextRequest } from "next/server";

const BACKEND = "http://localhost:5520";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const backendPath = path.join("/");
  const res = await fetch(`${BACKEND}/api/download/${backendPath}`, {
    cache: "no-store",
  });

  return new Response(res.body, {
    status: res.status,
    headers: {
      "Content-Type": res.headers.get("Content-Type") || "application/zip",
      "Content-Disposition":
        res.headers.get("Content-Disposition") ||
        `attachment; filename=download.zip`,
    },
  });
}
