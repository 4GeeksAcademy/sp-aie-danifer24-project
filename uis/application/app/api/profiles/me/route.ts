export async function PUT(request: Request) {
  const authorization = request.headers.get("authorization");
  if (!authorization) return Response.json({ detail: "Inicia sesión para editar tu perfil." }, { status: 401 });

  let input: unknown;
  try {
    input = await request.json();
  } catch {
    return Response.json({ detail: "Los datos enviados no son válidos." }, { status: 400 });
  }

  const apiUrl = (process.env.SUPPLIERS_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  try {
    const response = await fetch(`${apiUrl}/profiles/me`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: authorization },
      body: JSON.stringify(input),
      cache: "no-store",
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json({ detail: "El servicio de perfiles no está disponible." }, { status: 502 });
  }
}