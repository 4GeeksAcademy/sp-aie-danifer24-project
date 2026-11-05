const API_BASE = (process.env.SUPPLIERS_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export async function forwardReportingRequest(request: Request, path: string): Promise<Response> {
  const token = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
  if (!token) {
    return Response.json({ detail: "Inicia sesión para consultar el reporte." }, { status: 401 });
  }

  const incoming = new URL(request.url);
  const headers = new Headers({
    Accept: request.headers.get("accept") ?? "application/json",
    Authorization: `Bearer ${token}`,
  });

  try {
    const response = await fetch(`${API_BASE}${path}${incoming.search}`, {
      method: "GET",
      headers,
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
    return Response.json(
      { detail: "El servicio de reportes no está disponible ahora. Inténtalo de nuevo más tarde." },
      { status: 502 },
    );
  }
}
