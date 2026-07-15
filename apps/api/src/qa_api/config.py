from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str = "local"
    log_level: str = "INFO"
    database_url: str = "sqlite+pysqlite:///./.local/qa.db"
    auto_create_schema: bool = True
    seed_demo_data: bool = True
    dev_auth_enabled: bool = False
    oidc_issuer: str = "https://dev-idp.invalid/"
    oidc_audience: str = "enterprise-qa-api"
    oidc_jwks_url: str | None = None
    dev_jwt_secret: str | None = None
    cursor_signing_key: str | None = None
    jwt_leeway_seconds: int = 30
    max_request_bytes: int = 1_048_576

    @classmethod
    def from_env(cls) -> Settings:
        app_env = os.getenv("QA_APP_ENV", "local").strip().lower()
        settings = cls(
            app_env=app_env,
            log_level=os.getenv("QA_LOG_LEVEL", "INFO").upper(),
            database_url=os.getenv("QA_DATABASE_URL", "sqlite+pysqlite:///./.local/qa.db"),
            auto_create_schema=_as_bool(
                os.getenv("QA_AUTO_CREATE_SCHEMA"), app_env in {"local", "test"}
            ),
            seed_demo_data=_as_bool(os.getenv("QA_SEED_DEMO_DATA"), app_env in {"local", "test"}),
            dev_auth_enabled=_as_bool(os.getenv("QA_DEV_AUTH_ENABLED"), False),
            oidc_issuer=os.getenv("QA_OIDC_ISSUER", "https://dev-idp.invalid/"),
            oidc_audience=os.getenv("QA_OIDC_AUDIENCE", "enterprise-qa-api"),
            oidc_jwks_url=os.getenv("QA_OIDC_JWKS_URL") or None,
            dev_jwt_secret=os.getenv("QA_DEV_JWT_SECRET") or None,
            cursor_signing_key=os.getenv("QA_CURSOR_SIGNING_KEY") or None,
            jwt_leeway_seconds=int(os.getenv("QA_JWT_LEEWAY_SECONDS", "30")),
            max_request_bytes=int(os.getenv("QA_MAX_REQUEST_BYTES", "1048576")),
        )
        return settings.validated()

    def validated(self) -> Settings:
        if self.app_env not in {"local", "test", "dev", "staging", "production"}:
            raise ValueError("QA_APP_ENV must be local/test/dev/staging/production")
        if self.app_env in {"staging", "production"} and self.dev_auth_enabled:
            raise ValueError("development JWTs are forbidden outside local/test/dev")
        if self.app_env == "production" and self.auto_create_schema:
            raise ValueError("production schema changes must run through migrations")
        if self.dev_auth_enabled and (self.dev_jwt_secret is None or len(self.dev_jwt_secret) < 32):
            raise ValueError("QA_DEV_JWT_SECRET must contain at least 32 characters")
        if not self.dev_auth_enabled and not self.oidc_jwks_url:
            if self.app_env not in {"local", "test"}:
                raise ValueError("QA_OIDC_JWKS_URL is required when development auth is off")
        if self.cursor_signing_key is None:
            if self.app_env in {"staging", "production"}:
                raise ValueError("QA_CURSOR_SIGNING_KEY is required outside local development")
            object.__setattr__(self, "cursor_signing_key", secrets.token_urlsafe(32))
        if len(self.cursor_signing_key or "") < 32:
            raise ValueError("QA_CURSOR_SIGNING_KEY must contain at least 32 characters")
        if not 0 <= self.jwt_leeway_seconds <= 300:
            raise ValueError("QA_JWT_LEEWAY_SECONDS must be between 0 and 300")
        if not 1_024 <= self.max_request_bytes <= 10_485_760:
            raise ValueError("QA_MAX_REQUEST_BYTES must be between 1 KiB and 10 MiB")
        return self
