export type AuthEndpoint = "me" | "login" | "forgot-password" | "reset-password" | "change-password";

export async function forwardAuth(request: Request, endpoint: AuthEndpoint): Promise<Response> {
  const authorization = request.headers.get("authorization");
  if ((endpoint === "me" || endpoint === "change-password") && !authorization) {
    return Response.json({ detail: "Inicia sesión para continuar." }, { status: 401 });
  }
  let body: string | undefined;
  if (endpoint !== "me") {
    try {
      body = JSON.stringify(await request.json());
    } catch {
      return Response.json({ detail: "Los datos enviados no son válidos." }, { status: 400 });
    }
  }
  const apiUrl = (process.env.SUPPLIERS_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  try {
    const response = await fetch(`${apiUrl}/auth/${endpoint}`, {
      method: endpoint === "me" ? "GET" : "POST",
      headers: { "Content-Type": "application/json", ...(authorization ? { Authorization: authorization } : {}) },
      body,
      cache: "no-store",
      signal: request.signal,
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "Content-Type": response.headers.get("content-type") ?? "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ detail: "El servicio de autenticación no está disponible." }, { status: 502 });
  }
}