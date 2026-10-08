import { forwardIncidentRequest } from "../../../lib/incidents-proxy";

export function GET(request: Request) {
  return forwardIncidentRequest(request);
}

export function POST(request: Request) {
  return forwardIncidentRequest(request);
}
