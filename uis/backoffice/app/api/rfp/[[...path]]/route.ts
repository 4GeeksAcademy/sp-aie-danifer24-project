import { forwardApiRequest } from "@/lib/api-proxy";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const { path } = await params;
  return forwardApiRequest(request, `rfp/${(path ?? []).join("/")}`, true);
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const { path } = await params;
  return forwardApiRequest(request, `rfp/${(path ?? []).join("/")}`, true);
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const { path } = await params;
  return forwardApiRequest(request, `rfp/${(path ?? []).join("/")}`, true);
}