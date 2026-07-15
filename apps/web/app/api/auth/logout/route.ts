import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const csrfCookie = request.cookies.get("qa_csrf")?.value;
  const csrfHeader = request.headers.get("x-csrf-token");
  if (!csrfCookie || !csrfHeader || csrfCookie !== csrfHeader) {
    return NextResponse.json({ code: "CSRF_REJECTED" }, { status: 403 });
  }
  const response = NextResponse.json({ status: "signed_out" });
  response.cookies.delete("qa_access_token");
  response.cookies.delete("qa_csrf");
  return response;
}
