import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const apiUrl = process.env.QA_API_INTERNAL_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(`${apiUrl}/api/v1/health/ready`, { cache: "no-store" });
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json({ status: "unavailable" }, { status: 503 });
  }
}
