from __future__ import annotations

import base64
import hashlib
import os
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _integer_b64url(value: int) -> str:
    size = (value.bit_length() + 7) // 8
    return _b64url(value.to_bytes(size, "big"))


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    issuer: str
    audience: str
    client_id: str
    redirect_uri: str

    @classmethod
    def from_env(cls) -> ProviderSettings:
        issuer = os.getenv("FAKE_OIDC_ISSUER", "http://127.0.0.1:9002/")
        if not issuer.endswith("/"):
            issuer += "/"
        return cls(
            issuer=issuer,
            audience=os.getenv("FAKE_OIDC_AUDIENCE", "enterprise-qa-api"),
            client_id=os.getenv("FAKE_OIDC_CLIENT_ID", "enterprise-qa-web"),
            redirect_uri=os.getenv(
                "FAKE_OIDC_REDIRECT_URI",
                "http://127.0.0.1:3000/api/auth/callback",
            ),
        )


@dataclass(frozen=True, slots=True)
class AuthorizationGrant:
    client_id: str
    redirect_uri: str
    code_challenge: str
    subject: str
    tenant_id: str
    expires_at: float


PERSONAS = {
    "demo": ("demo-employee", "00000000-0000-7000-8000-000000000001"),
    "governance": ("governance-admin", "00000000-0000-7000-8000-000000000001"),
    "approver": ("config-approver", "00000000-0000-7000-8000-000000000001"),
    "auditor": ("demo-auditor", "00000000-0000-7000-8000-000000000001"),
    "release": ("release-manager", "00000000-0000-7000-8000-000000000001"),
    "product": ("product-approver", "00000000-0000-7000-8000-000000000001"),
    "business": ("business-approver", "00000000-0000-7000-8000-000000000001"),
    "data": ("data-approver", "00000000-0000-7000-8000-000000000001"),
    "security": ("security-approver", "00000000-0000-7000-8000-000000000001"),
    "sre": ("sre-approver", "00000000-0000-7000-8000-000000000001"),
    "other": ("other-employee", "00000000-0000-7000-8000-000000000002"),
    "disabled": ("disabled-employee", "00000000-0000-7000-8000-000000000001"),
}


class AuthorizationCodeStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, AuthorizationGrant] = {}

    def issue(self, grant: AuthorizationGrant) -> str:
        code = secrets.token_urlsafe(32)
        with self._lock:
            self._items[code] = grant
        return code

    def consume(self, code: str) -> AuthorizationGrant:
        with self._lock:
            grant = self._items.pop(code, None)
        if grant is None or grant.expires_at < monotonic():
            raise HTTPException(status_code=400, detail="invalid or expired authorization code")
        return grant


def create_app(settings: ProviderSettings | None = None) -> FastAPI:
    config = settings or ProviderSettings.from_env()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()
    modulus = _integer_b64url(public_numbers.n)
    exponent = _integer_b64url(public_numbers.e)
    key_id = hashlib.sha256(modulus.encode("ascii")).hexdigest()[:16]
    code_store = AuthorizationCodeStore()

    app = FastAPI(title="Enterprise QA Local Fake OIDC", docs_url=None, redoc_url=None)

    @app.get("/.well-known/openid-configuration")
    def discovery() -> dict[str, object]:
        return {
            "issuer": config.issuer,
            "authorization_endpoint": f"{config.issuer}authorize",
            "token_endpoint": f"{config.issuer}token",
            "jwks_uri": f"{config.issuer}jwks",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "subject_types_supported": ["public"],
        }

    @app.get("/jwks")
    def jwks() -> dict[str, object]:
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": key_id,
                    "n": modulus,
                    "e": exponent,
                }
            ]
        }

    @app.get("/authorize")
    def authorize(
        response_type: str,
        client_id: str,
        redirect_uri: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
        persona: str = Query(default="demo"),
    ) -> RedirectResponse:
        if response_type != "code":
            raise HTTPException(status_code=400, detail="only authorization code is supported")
        if client_id != config.client_id or redirect_uri != config.redirect_uri:
            raise HTTPException(status_code=400, detail="client or redirect URI is invalid")
        if code_challenge_method != "S256" or len(code_challenge) < 43:
            raise HTTPException(status_code=400, detail="S256 PKCE is required")
        if len(state) < 16:
            raise HTTPException(status_code=400, detail="state is invalid")
        identity = PERSONAS.get(persona)
        if identity is None:
            raise HTTPException(status_code=400, detail="persona is invalid")
        subject, tenant_id = identity
        code = code_store.issue(
            AuthorizationGrant(
                client_id=client_id,
                redirect_uri=redirect_uri,
                code_challenge=code_challenge,
                subject=subject,
                tenant_id=tenant_id,
                expires_at=monotonic() + 120,
            )
        )
        parts = urlsplit(redirect_uri)
        query = urlencode({"code": code, "state": state})
        location = urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
        return RedirectResponse(location, status_code=302)

    @app.post("/token")
    async def token(request: Request) -> JSONResponse:
        if request.headers.get("content-type", "").split(";", 1)[0] != (
            "application/x-www-form-urlencoded"
        ):
            raise HTTPException(status_code=415, detail="form encoding is required")
        form = parse_qs((await request.body()).decode("utf-8"), strict_parsing=True)

        def field(name: str) -> str:
            values = form.get(name)
            if values is None or len(values) != 1 or not values[0]:
                raise HTTPException(status_code=400, detail=f"{name} is required")
            return values[0]

        if field("grant_type") != "authorization_code":
            raise HTTPException(status_code=400, detail="grant type is invalid")
        code = field("code")
        client_id = field("client_id")
        redirect_uri = field("redirect_uri")
        verifier = field("code_verifier")
        grant = code_store.consume(code)
        expected_challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        if not secrets.compare_digest(expected_challenge, grant.code_challenge):
            raise HTTPException(status_code=400, detail="PKCE verification failed")
        if client_id != grant.client_id or redirect_uri != grant.redirect_uri:
            raise HTTPException(status_code=400, detail="authorization binding failed")
        now = datetime.now(UTC)
        claims = {
            "iss": config.issuer,
            "aud": config.audience,
            "sub": grant.subject,
            "tenant_id": grant.tenant_id,
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "jti": str(uuid4()),
        }
        access_token = jwt.encode(
            claims,
            private_key,
            algorithm="RS256",
            headers={"kid": key_id, "typ": "JWT"},
        )
        return JSONResponse(
            {
                "access_token": access_token,
                "id_token": access_token,
                "token_type": "Bearer",
                "expires_in": 1800,
                "scope": "openid profile qa:ask",
            },
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    @app.get("/health/live")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
