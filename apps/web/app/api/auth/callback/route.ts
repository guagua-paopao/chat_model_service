import { randomBytes } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
};

function failed(publicUrl: string) {
  const response = NextResponse.redirect(new URL("/?auth_error=login_failed", publicUrl));
  response.cookies.delete("qa_oidc_state");
  response.cookies.delete("qa_pkce_verifier");
  return response;
}

export async function GET(request: NextRequest) {
  const publicUrl = process.env.QA_WEB_PUBLIC_URL ?? "http://127.0.0.1:3000";
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  const expectedState = request.cookies.get("qa_oidc_state")?.value;
  const verifier = request.cookies.get("qa_pkce_verifier")?.value;
  if (!code || !state || !expectedState || state !== expectedState || !verifier) {
    return failed(publicUrl);
  }
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: process.env.QA_OIDC_CLIENT_ID ?? "enterprise-qa-web",
    redirect_uri: `${publicUrl}/api/auth/callback`,
    code,
    code_verifier: verifier,
  });
  try {
    const tokenEndpoint =
      process.env.QA_OIDC_TOKEN_URL_INTERNAL ?? "http://127.0.0.1:9002/token";
    const tokenResponse = await fetch(tokenEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
      cache: "no-store",
    });
    if (!tokenResponse.ok) return failed(publicUrl);
    const token = (await tokenResponse.json()) as TokenResponse;
    if (!token.access_token || token.token_type.toLowerCase() !== "bearer") {
      return failed(publicUrl);
    }
    const response = NextResponse.redirect(new URL("/", publicUrl));
    const secure =
      process.env.QA_COOKIE_SECURE === undefined
        ? process.env.NODE_ENV === "production"
        : process.env.QA_COOKIE_SECURE === "true";
    response.cookies.set("qa_access_token", token.access_token, {
      httpOnly: true,
      secure,
      sameSite: "lax",
      path: "/",
      maxAge: Math.min(token.expires_in, 1800),
    });
    response.cookies.set("qa_csrf", randomBytes(24).toString("base64url"), {
      httpOnly: false,
      secure,
      sameSite: "strict",
      path: "/",
      maxAge: Math.min(token.expires_in, 1800),
    });
    response.cookies.delete("qa_oidc_state");
    response.cookies.delete("qa_pkce_verifier");
    return response;
  } catch {
    return failed(publicUrl);
  }
}
