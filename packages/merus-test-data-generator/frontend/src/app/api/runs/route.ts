const BACKEND = "http://localhost:5520";

export async function GET() {
  const res = await fetch(`${BACKEND}/api/runs`, {
    cache: "no-store",
  });
  const data = await res.text();
  return new Response(data, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
