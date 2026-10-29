import { forwardApiRequest } from "../../../../lib/api-proxy";

export function PUT(request: Request) {
  return forwardApiRequest(request, "profiles/me", true);
}