import { forwardApiRequest } from "../../../lib/api-proxy";

export function GET(request: Request) {
  return forwardApiRequest(request, "suppliers", true);
}

export function POST(request: Request) {
  return forwardApiRequest(request, "suppliers", true);
}