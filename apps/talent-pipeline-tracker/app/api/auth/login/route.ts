import { forwardAuth } from "../../../../../../packages/shared/auth/proxy";

export function POST(request: Request) {
  return forwardAuth(request, "login");
}