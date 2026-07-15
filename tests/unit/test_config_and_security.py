from __future__ import annotations

import secrets
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import jwt
from qa_api.config import Settings
from qa_api.domain import ApiError
from qa_api.persistence import DEMO_TENANT_ID
from qa_api.security import TokenVerifier

SECRET = secrets.token_urlsafe(32)


def settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        auto_create_schema=True,
        seed_demo_data=True,
        dev_auth_enabled=True,
        oidc_issuer="https://test-idp.example.invalid/",
        oidc_audience="enterprise-qa-api-test",
        dev_jwt_secret=SECRET,
        cursor_signing_key="unit-test-cursor-signing-key-value-0001",
        jwt_leeway_seconds=0,
        fake_embedding_enabled=True,
    ).validated()


def token_for(
    config: Settings,
    *,
    subject: str = "demo-employee",
    tenant_id: str = str(DEMO_TENANT_ID),
    issuer: str | None = None,
    audience: str | None = None,
    expires_delta: timedelta = timedelta(minutes=5),
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": issuer or config.oidc_issuer,
            "aud": audience or config.oidc_audience,
            "sub": subject,
            "tenant_id": tenant_id,
            "iat": now - timedelta(seconds=1),
            "exp": now + expires_delta,
        },
        config.dev_jwt_secret,
        algorithm="HS256",
    )


class SettingsTests(unittest.TestCase):
    def test_production_rejects_development_auth(self) -> None:
        with self.assertRaises(ValueError):
            replace(settings(), app_env="production").validated()

    def test_short_cursor_key_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            replace(settings(), cursor_signing_key="short").validated()


class TokenVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = settings()
        self.verifier = TokenVerifier(self.settings)

    def test_valid_signed_token_builds_trusted_identity(self) -> None:
        identity = self.verifier.verify(token_for(self.settings))
        self.assertEqual(identity.tenant_id, DEMO_TENANT_ID)
        self.assertEqual(identity.subject, "demo-employee")

    def test_expired_token_is_rejected(self) -> None:
        with self.assertRaises(ApiError) as context:
            self.verifier.verify(token_for(self.settings, expires_delta=timedelta(minutes=-1)))
        self.assertEqual(context.exception.code, "TOKEN_EXPIRED")

    def test_wrong_issuer_is_rejected(self) -> None:
        with self.assertRaises(ApiError):
            self.verifier.verify(token_for(self.settings, issuer="https://attacker.invalid/"))

    def test_wrong_audience_is_rejected(self) -> None:
        with self.assertRaises(ApiError):
            self.verifier.verify(token_for(self.settings, audience="other-api"))

    def test_unsigned_token_is_rejected(self) -> None:
        now = datetime.now(UTC)
        unsigned = jwt.encode(
            {
                "iss": self.settings.oidc_issuer,
                "aud": self.settings.oidc_audience,
                "sub": "demo-employee",
                "tenant_id": str(DEMO_TENANT_ID),
                "iat": now,
                "exp": now + timedelta(minutes=5),
            },
            key="",
            algorithm="none",
        )
        with self.assertRaises(ApiError):
            self.verifier.verify(unsigned)


if __name__ == "__main__":
    unittest.main()
