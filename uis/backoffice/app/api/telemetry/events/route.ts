const developmentTelemetryEndpoint = "http://127.0.0.1:8000/telemetry/events";

export async function POST(request: Request) {
  const endpoint = process.env.TELEMETRY_ENDPOINT
    || (process.env.NODE_ENV === "development" ? developmentTelemetryEndpoint : null);
  if (!endpoint) {
    return Response.json({ detail: "Telemetry receiver is not configured." }, { status: 503 });
  }
  let body: string;
  try {
    body = await request.text();
    const payload: unknown = JSON.parse(body);
    if (!payload || typeof payload !== "object" || !("events" in payload) || !Array.isArray(payload.events)) {
      return Response.json({ detail: "Invalid telemetry batch." }, { status: 400 });
    }
  } catch {
    return Response.json({ detail: "Invalid telemetry batch." }, { status: 400 });
  }

  try {
    const upstream = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body,
      cache: "no-store",
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("Content-Type") || "application/json" },
    });
  } catch {
    return Response.json({ detail: "Telemetry receiver unavailable." }, { status: 502 });
  }
}