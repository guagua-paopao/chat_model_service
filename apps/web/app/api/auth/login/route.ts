import { createHash, randomBytes } from "node:crypto";
import { NextResponse } from "next/server";

function base64url(value: Buffer) {
  return value.toString("base64url");
}

export async function GET() {
  const state = base64url(randomBytes(24));
  const verifier = base64url(randomBytes(48));
  const challenge = base64url(createHash("sha256").update(verifier).digest());
  const publicUrl = process.env.QA_WEB_PUBLIC_URL ?? "http://127.0.0.1:3000";
  const authorizationUrl = new URL(
    process.env.QA_OIDC_AUTHORIZATION_URL ?? "http://127.0.0.1:9002/authorize",
  );
  authorizationUrl.searchParams.set("response_type", "code");
  authorizationUrl.searchParams.set(
    "client_id",
    process.env.QA_OIDC_CLIENT_ID ?? "enterprise-qa-web",
  );
  authorizationUrl.searchParams.set("redirect_uri", `${publicUrl}/api/auth/callback`);
  authorizationUrl.searchParams.set("scope", "openid profile qa:ask");
  authorizationUrl.searchParams.set("state", state);
  authorizationUrl.searchParams.set("code_challenge", challenge);
  authorizationUrl.searchParams.set("code_challenge_method", "S256");
  if (process.env.QA_OIDC_DEV_PERSONA) {
    authorizationUrl.searchParams.set("persona", process.env.QA_OIDC_DEV_PERSONA);
  }
  const response = NextResponse.redirect(authorizationUrl);
  const secure =
    process.env.QA_COOKIE_SECURE === undefined
      ? process.env.NODE_ENV === "production"
      : process.env.QA_COOKIE_SECURE === "true";
  const transient = {
    httpOnly: true,
    secure,
    sameSite: "lax" as const,
    maxAge: 300,
    path: "/api/auth",
  };
  response.cookies.set("qa_oidc_state", state, transient);
  response.cookies.set("qa_pkce_verifier", verifier, transient);
  return response;
}
