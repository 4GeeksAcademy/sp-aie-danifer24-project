const API_BASE = (process.env.NEXT_PUBLIC_INVENTORY_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export async function forwardInventoryRequest(request: Request, suffix: string): Promise<Response> {
  const incoming = new URL(request.url);
  const target = `${API_BASE}/inventory/${suffix}${incoming.search}`;
  const headers = new Headers();
  const authorization = request.headers.get("authorization");
  const method = request.method.toUpperCase();
  const protectedRoute = method !== "GET" || suffix === "orders";

  if (authorization) headers.set("Authorization", authorization);
  headers.set("Accept", request.headers.get("accept") ?? "application/json");
  if (request.headers.has("content-type")) {
    headers.set("Content-Type", request.headers.get("content-type")!);
  }

  if (protectedRoute && !authorization) {
    return Response.json({ detail: "Inicia sesión para continuar." }, { status: 401 });
  }

  try {
    const response = await fetch(target, {
      method,
      headers,
      body: method === "GET" || method === "HEAD" ? undefined : await request.text(),
      cache: "no-store",
      signal: request.signal,
    });
    return new Response(response.body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json({ detail: "El servicio de inventario no está disponible." }, { status: 502 });
  }

}