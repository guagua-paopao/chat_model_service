import { cookies, headers } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const UUID = "[0-9a-f-]{36}";
const ALLOWED_PATH = new RegExp(
  `^(me|models|conversations(?:/${UUID})?|chat/completions|messages/${UUID}/(?:cancel|retry)|knowledge-bases(?:/${UUID}/documents)?|documents/${UUID}(?:/versions|/upload-complete)?|ingestion-jobs/${UUID}(?:/retry)?|retrieval/search|uploads/${UUID}/content)$`,
);
const SAFE_METHODS = new Set(["GET", "HEAD"]);

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const params = await context.params;
  const path = params.path.join("/");
  if (!ALLOWED_PATH.test(path)) {
    return NextResponse.json({ code: "BFF_PATH_DENIED" }, { status: 404 });
  }
  const cookieStore = await cookies();
  const token = cookieStore.get("qa_access_token")?.value;
  if (!token) {
    return NextResponse.json({ code: "AUTH_REQUIRED" }, { status: 401 });
  }
  if (!SAFE_METHODS.has(request.method)) {
    const csrfCookie = cookieStore.get("qa_csrf")?.value;
    const csrfHeader = (await headers()).get("x-csrf-token");
    if (!csrfCookie || !csrfHeader || csrfCookie !== csrfHeader) {
      return NextResponse.json({ code: "CSRF_REJECTED" }, { status: 403 });
    }
  }
  const target = new URL(
    `/api/v1/${path}${request.nextUrl.search}`,
    process.env.QA_API_INTERNAL_URL ?? "http://localhost:8000",
  );
  const outgoing = new Headers({ Authorization: `Bearer ${token}` });
  const contentType = request.headers.get("content-type");
  const ifMatch = request.headers.get("if-match");
  const requestId = request.headers.get("x-request-id");
  const idempotencyKey = request.headers.get("idempotency-key");
  if (contentType) outgoing.set("Content-Type", contentType);
  if (ifMatch) outgoing.set("If-Match", ifMatch);
  if (requestId) outgoing.set("X-Request-ID", requestId);
  if (idempotencyKey) outgoing.set("Idempotency-Key", idempotencyKey);
  const response = await fetch(target, {
    method: request.method,
    headers: outgoing,
    body: SAFE_METHODS.has(request.method) ? undefined : await request.arrayBuffer(),
    cache: "no-store",
  });
  const responseHeaders = new Headers({ "Cache-Control": "no-store" });
  for (const name of ["content-type", "etag", "location", "x-request-id", "x-trace-id"]) {
    const value = response.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new NextResponse(response.body, { status: response.status, headers: responseHeaders });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
