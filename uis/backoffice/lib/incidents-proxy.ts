const API_BASE = (process.env.SUPPLIERS_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export async function forwardIncidentRequest(request: Request, suffix = ""): Promise<Response> {
  const incoming = new URL(request.url);
  const target = `${API_BASE}/api/incidents${suffix}${incoming.search}`;
  const headers = new Headers();
  const token = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  headers.set("Accept", request.headers.get("accept") ?? "application/json");
  if (request.headers.has("content-type")) headers.set("Content-Type", request.headers.get("content-type")!);

  try {
    if (!token) return Response.json({ detail: "Inicia sesión para continuar." }, { status: 401 });
    const response = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.text(),
      cache: "no-store",
      signal: request.signal,
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json({ detail: "El servicio de incidencias no está disponible." }, { status: 502 });
  }
}
