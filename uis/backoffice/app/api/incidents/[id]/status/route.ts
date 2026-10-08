import { forwardIncidentRequest } from "../../../../../lib/incidents-proxy";

export async function PATCH(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  return forwardIncidentRequest(request, `/${encodeURIComponent(id)}/status`);
}
