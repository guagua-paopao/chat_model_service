from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt

from qa_api.config import Settings
from qa_api.domain import ApiError


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    issuer: str
    subject: str
    tenant_id: UUID


class TokenVerifier:
    """Validate signed JWTs; decoding without validation is never an auth decision."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jwks_client = (
            jwt.PyJWKClient(settings.oidc_jwks_url, cache_keys=True, lifespan=300)
            if settings.oidc_jwks_url
            else None
        )

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            if algorithm == "HS256" and self._settings.dev_auth_enabled:
                dev_secret = self._settings.dev_jwt_secret
                if dev_secret is None:
                    raise jwt.InvalidKeyError("development signing key is missing")
                claims = jwt.decode(
                    token,
                    dev_secret,
                    algorithms=["HS256"],
                    audience=self._settings.oidc_audience,
                    issuer=self._settings.oidc_issuer,
                    leeway=self._settings.jwt_leeway_seconds,
                    options={"require": ["exp", "iat", "iss", "aud", "sub", "tenant_id"]},
                )
            elif algorithm == "RS256" and self._jwks_client is not None:
                key = self._jwks_client.get_signing_key_from_jwt(token)
                claims = jwt.decode(
                    token,
                    key.key,
                    algorithms=["RS256"],
                    audience=self._settings.oidc_audience,
                    issuer=self._settings.oidc_issuer,
                    leeway=self._settings.jwt_leeway_seconds,
                    options={"require": ["exp", "iat", "iss", "aud", "sub", "tenant_id"]},
                )
            else:
                raise jwt.InvalidAlgorithmError("algorithm is not allowed")
            return self._identity_from_claims(claims)
        except jwt.ExpiredSignatureError as exc:
            raise ApiError(
                401, "TOKEN_EXPIRED", "Authentication required", "Access token expired."
            ) from exc
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise ApiError(
                401, "TOKEN_INVALID", "Authentication required", "Access token is invalid."
            ) from exc

    @staticmethod
    def _identity_from_claims(claims: dict[str, Any]) -> VerifiedIdentity:
        issuer = claims.get("iss")
        subject = claims.get("sub")
        tenant_claim = claims.get("tenant_id")
        if not isinstance(issuer, str) or not issuer:
            raise ValueError("issuer missing")
        if not isinstance(subject, str) or not subject:
            raise ValueError("subject missing")
        if not isinstance(tenant_claim, str):
            raise ValueError("tenant missing")
        return VerifiedIdentity(
            issuer=issuer,
            subject=subject,
            tenant_id=UUID(tenant_claim),
        )


def bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise ApiError(401, "AUTH_REQUIRED", "Authentication required", "Bearer token is required.")
    scheme, separator, value = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not value.strip():
        raise ApiError(
            401,
            "AUTH_SCHEME_INVALID",
            "Authentication required",
            "Authorization must use the Bearer scheme.",
        )
    return value.strip()
