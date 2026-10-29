import { forwardAuth, type AuthEndpoint } from "../../../../../../packages/shared/auth/proxy";

const endpoints = new Set<AuthEndpoint>(["forgot-password", "reset-password", "change-password"]);

type RouteContext = { params: Promise<{ endpoint: string[] }> };

export async function POST(request: Request, context: RouteContext) {
  const { endpoint } = await context.params;
  if (endpoint.length !== 1 || !endpoints.has(endpoint[0] as AuthEndpoint)) {
    return Response.json({ detail: "Endpoint de autenticación no encontrado." }, { status: 404 });
  }
  return forwardAuth(request, endpoint[0] as AuthEndpoint);
}