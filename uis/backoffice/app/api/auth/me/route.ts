import { forwardAuth } from "../../../../../../packages/shared/auth/proxy";

export function GET(request: Request) {
  return forwardAuth(request, "me");
}