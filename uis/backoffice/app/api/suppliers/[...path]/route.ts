import { forwardApiRequest } from "../../../../lib/api-proxy";

type RouteContext = { params: Promise<{ path: string[] }> };

async function forward(request: Request, context: RouteContext) {
  const { path } = await context.params;
  return forwardApiRequest(request, `suppliers/${path.map(encodeURIComponent).join("/")}`, true);
}

export const GET = forward;
export const PATCH = forward;
export const DELETE = forward;