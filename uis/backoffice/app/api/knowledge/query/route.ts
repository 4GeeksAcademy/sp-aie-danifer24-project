import { forwardApiRequest } from "../../../../lib/api-proxy";

export function POST(request: Request) {
  return forwardApiRequest(request, "agent/query", true);
}
