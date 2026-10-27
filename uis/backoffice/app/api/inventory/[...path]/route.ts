import { forwardInventoryRequest } from "../../../../lib/inventory-proxy";

type RouteContext = { params: Promise<{ path: string[] }> };

async function forward(request: Request, context: RouteContext) {
  const { path } = await context.params;
  return forwardInventoryRequest(request, path.map(encodeURIComponent).join("/"));
}

export const GET = forward;
export const POST = forward;
