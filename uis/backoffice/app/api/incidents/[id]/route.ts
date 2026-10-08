import { forwardIncidentRequest } from "../../../../lib/incidents-proxy";

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  return forwardIncidentRequest(request, `/${encodeURIComponent(id)}`);
}
