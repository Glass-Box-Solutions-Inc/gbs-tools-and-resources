import { NextRequest } from "next/server";

const BACKEND = "http://localhost:5520";

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const endpoint = url.searchParams.get("endpoint") || "types";

  let backendUrl: string;
  if (endpoint === "subtypes") {
    const docType = url.searchParams.get("docType");
    backendUrl = docType
      ? `${BACKEND}/api/taxonomy/subtypes/${docType}`
      : `${BACKEND}/api/taxonomy/subtypes`;
  } else {
    backendUrl = `${BACKEND}/api/taxonomy/types`;
  }

  const res = await fetch(backendUrl, { cache: "no-store" });
  const data = await res.text();
  return new Response(data, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
