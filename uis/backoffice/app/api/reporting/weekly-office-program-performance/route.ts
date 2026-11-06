import { forwardReportingRequest } from "../../../../lib/reporting-proxy";

export function GET(request: Request) {
  return forwardReportingRequest(request, "/reporting/weekly-office-program-performance");
}
