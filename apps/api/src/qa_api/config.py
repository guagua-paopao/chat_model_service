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
    fake_model_enabled: bool = False
    model_provider_enabled: bool = False
    model_provider_base_url: str | None = None
    model_provider_api_key: str | None = None
    model_provider_model: str | None = None
    model_connect_timeout_seconds: float = 5.0
    model_first_token_timeout_seconds: float = 10.0
    model_total_timeout_seconds: float = 60.0
    model_max_attempts: int = 3
    model_max_concurrency: int = 8
    chat_requests_per_minute: int = 30
    chat_tenant_concurrency: int = 8
    chat_user_concurrency: int = 2
    chat_max_input_tokens: int = 4_096
    chat_max_output_tokens: int = 1_024
    fake_model_chunk_delay_ms: int = 40

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
            fake_model_enabled=_as_bool(
                os.getenv("QA_FAKE_MODEL_ENABLED"), app_env in {"local", "test", "dev"}
            ),
            model_provider_enabled=_as_bool(os.getenv("QA_MODEL_PROVIDER_ENABLED"), False),
            model_provider_base_url=os.getenv("QA_MODEL_PROVIDER_BASE_URL") or None,
            model_provider_api_key=os.getenv("QA_MODEL_PROVIDER_API_KEY") or None,
            model_provider_model=os.getenv("QA_MODEL_PROVIDER_MODEL") or None,
            model_connect_timeout_seconds=float(
                os.getenv("QA_MODEL_CONNECT_TIMEOUT_SECONDS", "5")
            ),
            model_first_token_timeout_seconds=float(
                os.getenv("QA_MODEL_FIRST_TOKEN_TIMEOUT_SECONDS", "10")
            ),
            model_total_timeout_seconds=float(os.getenv("QA_MODEL_TOTAL_TIMEOUT_SECONDS", "60")),
            model_max_attempts=int(os.getenv("QA_MODEL_MAX_ATTEMPTS", "3")),
            model_max_concurrency=int(os.getenv("QA_MODEL_MAX_CONCURRENCY", "8")),
            chat_requests_per_minute=int(os.getenv("QA_CHAT_REQUESTS_PER_MINUTE", "30")),
            chat_tenant_concurrency=int(os.getenv("QA_CHAT_TENANT_CONCURRENCY", "8")),
            chat_user_concurrency=int(os.getenv("QA_CHAT_USER_CONCURRENCY", "2")),
            chat_max_input_tokens=int(os.getenv("QA_CHAT_MAX_INPUT_TOKENS", "4096")),
            chat_max_output_tokens=int(os.getenv("QA_CHAT_MAX_OUTPUT_TOKENS", "1024")),
            fake_model_chunk_delay_ms=int(os.getenv("QA_FAKE_MODEL_CHUNK_DELAY_MS", "40")),
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
        if self.app_env in {"staging", "production"} and self.fake_model_enabled:
            raise ValueError("the fake model provider is forbidden outside local/test/dev")
        if self.model_provider_enabled:
            if not self.model_provider_base_url or not self.model_provider_base_url.startswith(
                "https://"
            ):
                raise ValueError("QA_MODEL_PROVIDER_BASE_URL must be an https URL")
            if not self.model_provider_api_key:
                raise ValueError("QA_MODEL_PROVIDER_API_KEY is required when provider is enabled")
            if not self.model_provider_model:
                raise ValueError("QA_MODEL_PROVIDER_MODEL is required when provider is enabled")
        if self.app_env in {"staging", "production"} and not self.model_provider_enabled:
            raise ValueError("an approved model provider is required outside local development")
        if not 0.1 <= self.model_connect_timeout_seconds <= 60:
            raise ValueError("QA_MODEL_CONNECT_TIMEOUT_SECONDS must be between 0.1 and 60")
        if not 0.1 <= self.model_first_token_timeout_seconds <= 120:
            raise ValueError("QA_MODEL_FIRST_TOKEN_TIMEOUT_SECONDS must be between 0.1 and 120")
        if not self.model_first_token_timeout_seconds <= self.model_total_timeout_seconds <= 600:
            raise ValueError("QA_MODEL_TOTAL_TIMEOUT_SECONDS must cover first token and be <= 600")
        if not 1 <= self.model_max_attempts <= 5:
            raise ValueError("QA_MODEL_MAX_ATTEMPTS must be between 1 and 5")
        if not 1 <= self.model_max_concurrency <= 256:
            raise ValueError("QA_MODEL_MAX_CONCURRENCY must be between 1 and 256")
        if not 1 <= self.chat_requests_per_minute <= 10_000:
            raise ValueError("QA_CHAT_REQUESTS_PER_MINUTE must be between 1 and 10000")
        if not 1 <= self.chat_user_concurrency <= self.chat_tenant_concurrency <= 1_000:
            raise ValueError("chat concurrency must satisfy user <= tenant <= 1000")
        if not 128 <= self.chat_max_input_tokens <= 1_000_000:
            raise ValueError("QA_CHAT_MAX_INPUT_TOKENS is outside the supported range")
        if not 16 <= self.chat_max_output_tokens <= 100_000:
            raise ValueError("QA_CHAT_MAX_OUTPUT_TOKENS is outside the supported range")
        if not 0 <= self.fake_model_chunk_delay_ms <= 10_000:
            raise ValueError("QA_FAKE_MODEL_CHUNK_DELAY_MS must be between 0 and 10000")
        return self
