const API_BASE = (process.env.SUPPLIERS_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export async function forwardApiRequest(request: Request, path: string, requireAuth = false): Promise<Response> {
  const authorization = request.headers.get("authorization");
  if (requireAuth && !authorization) {
    return Response.json({ detail: "Inicia sesión para continuar." }, { status: 401 });
  }

  const incoming = new URL(request.url);
  const method = request.method.toUpperCase();
  const headers = new Headers({ Accept: request.headers.get("accept") ?? "application/json" });
  if (authorization) headers.set("Authorization", authorization);
  if (request.headers.has("content-type")) headers.set("Content-Type", request.headers.get("content-type")!);

  try {
    const response = await fetch(`${API_BASE}/${path}${incoming.search}`, {
      method,
      headers,
      body: method === "GET" || method === "HEAD" ? undefined : await request.text(),
      cache: "no-store",
    });
    return new Response(response.body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json({ detail: "El servicio no está disponible." }, { status: 502 });
  }
}