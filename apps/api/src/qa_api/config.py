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
    object_store_backend: str = "local"
    object_store_local_root: str = ".local/objects"
    object_store_endpoint_url: str | None = None
    object_store_public_endpoint_url: str | None = None
    object_store_region: str = "us-east-1"
    object_store_access_key: str | None = None
    object_store_secret_key: str | None = None
    object_store_quarantine_bucket: str = "qa-quarantine"
    object_store_published_bucket: str = "qa-published"
    object_store_auto_create_buckets: bool = True
    upload_public_base_url: str = "http://127.0.0.1:3000/api/qa"
    upload_presign_seconds: int = 900
    ingestion_max_upload_bytes: int = 10_485_760
    ingestion_max_attempts: int = 3
    ingestion_job_lease_seconds: int = 120
    ingestion_worker_poll_seconds: float = 1.0
    malware_scanner_backend: str = "signature"
    clamav_host: str | None = None
    clamav_port: int = 3310
    clamav_timeout_seconds: float = 15.0
    chunk_max_tokens: int = 256
    chunk_overlap_tokens: int = 32
    fake_embedding_enabled: bool = False
    embedding_provider_enabled: bool = False
    embedding_provider_base_url: str | None = None
    embedding_provider_api_key: str | None = None
    embedding_provider_model: str | None = None
    embedding_dimensions: int = 16
    rag_enabled: bool = True
    retrieval_vector_candidates: int = 20
    retrieval_lexical_candidates: int = 20
    retrieval_rerank_candidates: int = 12
    retrieval_final_k: int = 5
    retrieval_rrf_k: int = 60
    retrieval_context_max_tokens: int = 1_200
    retrieval_min_relevance: float = 0.28
    retrieval_min_query_coverage: float = 0.34
    citation_max_quote_chars: int = 1_200
    fake_reranker_enabled: bool = True
    reranker_provider_enabled: bool = False
    reranker_provider_base_url: str | None = None
    reranker_provider_api_key: str | None = None
    reranker_provider_model: str | None = None
    reranker_timeout_seconds: float = 20.0
    local_governance_evaluator_enabled: bool = True

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
            object_store_backend=os.getenv("QA_OBJECT_STORE_BACKEND", "local").strip().lower(),
            object_store_local_root=os.getenv("QA_OBJECT_STORE_LOCAL_ROOT", ".local/objects"),
            object_store_endpoint_url=os.getenv("QA_OBJECT_STORE_ENDPOINT_URL") or None,
            object_store_public_endpoint_url=(
                os.getenv("QA_OBJECT_STORE_PUBLIC_ENDPOINT_URL") or None
            ),
            object_store_region=os.getenv("QA_OBJECT_STORE_REGION", "us-east-1"),
            object_store_access_key=os.getenv("QA_OBJECT_STORE_ACCESS_KEY") or None,
            object_store_secret_key=os.getenv("QA_OBJECT_STORE_SECRET_KEY") or None,
            object_store_quarantine_bucket=os.getenv(
                "QA_OBJECT_STORE_QUARANTINE_BUCKET", "qa-quarantine"
            ),
            object_store_published_bucket=os.getenv(
                "QA_OBJECT_STORE_PUBLISHED_BUCKET", "qa-published"
            ),
            object_store_auto_create_buckets=_as_bool(
                os.getenv("QA_OBJECT_STORE_AUTO_CREATE_BUCKETS"),
                app_env in {"local", "test", "dev"},
            ),
            upload_public_base_url=os.getenv(
                "QA_UPLOAD_PUBLIC_BASE_URL", "http://127.0.0.1:3000/api/qa"
            ),
            upload_presign_seconds=int(os.getenv("QA_UPLOAD_PRESIGN_SECONDS", "900")),
            ingestion_max_upload_bytes=int(
                os.getenv("QA_INGESTION_MAX_UPLOAD_BYTES", "10485760")
            ),
            ingestion_max_attempts=int(os.getenv("QA_INGESTION_MAX_ATTEMPTS", "3")),
            ingestion_job_lease_seconds=int(
                os.getenv("QA_INGESTION_JOB_LEASE_SECONDS", "120")
            ),
            ingestion_worker_poll_seconds=float(
                os.getenv("QA_INGESTION_WORKER_POLL_SECONDS", "1")
            ),
            malware_scanner_backend=os.getenv(
                "QA_MALWARE_SCANNER_BACKEND", "signature"
            ).strip().lower(),
            clamav_host=os.getenv("QA_CLAMAV_HOST") or None,
            clamav_port=int(os.getenv("QA_CLAMAV_PORT", "3310")),
            clamav_timeout_seconds=float(os.getenv("QA_CLAMAV_TIMEOUT_SECONDS", "15")),
            chunk_max_tokens=int(os.getenv("QA_CHUNK_MAX_TOKENS", "256")),
            chunk_overlap_tokens=int(os.getenv("QA_CHUNK_OVERLAP_TOKENS", "32")),
            fake_embedding_enabled=_as_bool(
                os.getenv("QA_FAKE_EMBEDDING_ENABLED"), app_env in {"local", "test", "dev"}
            ),
            embedding_provider_enabled=_as_bool(
                os.getenv("QA_EMBEDDING_PROVIDER_ENABLED"), False
            ),
            embedding_provider_base_url=os.getenv("QA_EMBEDDING_PROVIDER_BASE_URL") or None,
            embedding_provider_api_key=os.getenv("QA_EMBEDDING_PROVIDER_API_KEY") or None,
            embedding_provider_model=os.getenv("QA_EMBEDDING_PROVIDER_MODEL") or None,
            embedding_dimensions=int(os.getenv("QA_EMBEDDING_DIMENSIONS", "16")),
            rag_enabled=_as_bool(os.getenv("QA_RAG_ENABLED"), True),
            retrieval_vector_candidates=int(
                os.getenv("QA_RETRIEVAL_VECTOR_CANDIDATES", "20")
            ),
            retrieval_lexical_candidates=int(
                os.getenv("QA_RETRIEVAL_LEXICAL_CANDIDATES", "20")
            ),
            retrieval_rerank_candidates=int(
                os.getenv("QA_RETRIEVAL_RERANK_CANDIDATES", "12")
            ),
            retrieval_final_k=int(os.getenv("QA_RETRIEVAL_FINAL_K", "5")),
            retrieval_rrf_k=int(os.getenv("QA_RETRIEVAL_RRF_K", "60")),
            retrieval_context_max_tokens=int(
                os.getenv("QA_RETRIEVAL_CONTEXT_MAX_TOKENS", "1200")
            ),
            retrieval_min_relevance=float(
                os.getenv("QA_RETRIEVAL_MIN_RELEVANCE", "0.28")
            ),
            retrieval_min_query_coverage=float(
                os.getenv("QA_RETRIEVAL_MIN_QUERY_COVERAGE", "0.34")
            ),
            citation_max_quote_chars=int(os.getenv("QA_CITATION_MAX_QUOTE_CHARS", "1200")),
            fake_reranker_enabled=_as_bool(
                os.getenv("QA_FAKE_RERANKER_ENABLED"), app_env in {"local", "test", "dev"}
            ),
            reranker_provider_enabled=_as_bool(
                os.getenv("QA_RERANKER_PROVIDER_ENABLED"), False
            ),
            reranker_provider_base_url=os.getenv("QA_RERANKER_PROVIDER_BASE_URL") or None,
            reranker_provider_api_key=os.getenv("QA_RERANKER_PROVIDER_API_KEY") or None,
            reranker_provider_model=os.getenv("QA_RERANKER_PROVIDER_MODEL") or None,
            reranker_timeout_seconds=float(os.getenv("QA_RERANKER_TIMEOUT_SECONDS", "20")),
            local_governance_evaluator_enabled=_as_bool(
                os.getenv("QA_LOCAL_GOVERNANCE_EVALUATOR_ENABLED"),
                app_env in {"local", "test", "dev"},
            ),
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
        if self.object_store_backend not in {"local", "s3"}:
            raise ValueError("QA_OBJECT_STORE_BACKEND must be local or s3")
        if self.app_env in {"staging", "production"} and self.object_store_backend == "local":
            raise ValueError("local object storage is forbidden outside local/test/dev")
        if self.object_store_backend == "s3":
            if not self.object_store_endpoint_url or not self.object_store_public_endpoint_url:
                raise ValueError("S3 internal and public endpoints are required")
            if self.app_env in {"staging", "production"} and (
                not self.object_store_endpoint_url.startswith("https://")
                or not self.object_store_public_endpoint_url.startswith("https://")
            ):
                raise ValueError("production object storage endpoints must use https")
            if not self.object_store_access_key or not self.object_store_secret_key:
                raise ValueError("S3 object storage credentials are required")
        if self.object_store_quarantine_bucket == self.object_store_published_bucket:
            raise ValueError("quarantine and published buckets must be different")
        if self.app_env in {"staging", "production"} and self.object_store_auto_create_buckets:
            raise ValueError("production buckets must be provisioned outside the application")
        if not 60 <= self.upload_presign_seconds <= 3_600:
            raise ValueError("QA_UPLOAD_PRESIGN_SECONDS must be between 60 and 3600")
        if not 1_048_576 <= self.ingestion_max_upload_bytes <= 104_857_600:
            raise ValueError("QA_INGESTION_MAX_UPLOAD_BYTES must be between 1 MiB and 100 MiB")
        if not 1 <= self.ingestion_max_attempts <= 10:
            raise ValueError("QA_INGESTION_MAX_ATTEMPTS must be between 1 and 10")
        if not 30 <= self.ingestion_job_lease_seconds <= 3_600:
            raise ValueError("QA_INGESTION_JOB_LEASE_SECONDS must be between 30 and 3600")
        if not 0.1 <= self.ingestion_worker_poll_seconds <= 60:
            raise ValueError("QA_INGESTION_WORKER_POLL_SECONDS must be between 0.1 and 60")
        if self.malware_scanner_backend not in {"signature", "clamav"}:
            raise ValueError("QA_MALWARE_SCANNER_BACKEND must be signature or clamav")
        if self.app_env in {"staging", "production"} and self.malware_scanner_backend != "clamav":
            raise ValueError("an external ClamAV scanner is required outside local development")
        if self.malware_scanner_backend == "clamav" and not self.clamav_host:
            raise ValueError("QA_CLAMAV_HOST is required when ClamAV scanning is enabled")
        if not 1 <= self.clamav_port <= 65_535:
            raise ValueError("QA_CLAMAV_PORT is invalid")
        if not 0.1 <= self.clamav_timeout_seconds <= 120:
            raise ValueError("QA_CLAMAV_TIMEOUT_SECONDS must be between 0.1 and 120")
        if not 64 <= self.chunk_max_tokens <= 2_048:
            raise ValueError("QA_CHUNK_MAX_TOKENS must be between 64 and 2048")
        if not 0 <= self.chunk_overlap_tokens < self.chunk_max_tokens:
            raise ValueError("chunk overlap must be lower than chunk max tokens")
        if self.app_env in {"staging", "production"} and self.fake_embedding_enabled:
            raise ValueError("fake embeddings are forbidden outside local/test/dev")
        if self.embedding_provider_enabled:
            if (
                not self.embedding_provider_base_url
                or not self.embedding_provider_base_url.startswith("https://")
            ):
                raise ValueError("QA_EMBEDDING_PROVIDER_BASE_URL must be an https URL")
            if not self.embedding_provider_api_key or not self.embedding_provider_model:
                raise ValueError("embedding provider key and model are required")
        if self.app_env in {"staging", "production"} and not self.embedding_provider_enabled:
            raise ValueError("an approved embedding provider is required outside local development")
        if not 8 <= self.embedding_dimensions <= 4_096:
            raise ValueError("QA_EMBEDDING_DIMENSIONS must be between 8 and 4096")
        if not 1 <= self.retrieval_final_k <= self.retrieval_rerank_candidates <= 100:
            raise ValueError("retrieval ranks must satisfy final_k <= rerank_candidates <= 100")
        if not self.retrieval_rerank_candidates <= self.retrieval_vector_candidates <= 500:
            raise ValueError("vector candidate count must cover rerank candidates and be <= 500")
        if not self.retrieval_rerank_candidates <= self.retrieval_lexical_candidates <= 500:
            raise ValueError("lexical candidate count must cover rerank candidates and be <= 500")
        if not 1 <= self.retrieval_rrf_k <= 1_000:
            raise ValueError("QA_RETRIEVAL_RRF_K must be between 1 and 1000")
        if not 128 <= self.retrieval_context_max_tokens < self.chat_max_input_tokens:
            raise ValueError("RAG context budget must be >= 128 and below chat input budget")
        if not 0 <= self.retrieval_min_relevance <= 1:
            raise ValueError("QA_RETRIEVAL_MIN_RELEVANCE must be between 0 and 1")
        if not 0 <= self.retrieval_min_query_coverage <= 1:
            raise ValueError("QA_RETRIEVAL_MIN_QUERY_COVERAGE must be between 0 and 1")
        if not 200 <= self.citation_max_quote_chars <= 4_000:
            raise ValueError("QA_CITATION_MAX_QUOTE_CHARS must be between 200 and 4000")
        if self.fake_reranker_enabled and self.reranker_provider_enabled:
            raise ValueError("fake and provider rerankers cannot both be enabled")
        if self.app_env in {"staging", "production"} and self.fake_reranker_enabled:
            raise ValueError("the fake reranker is forbidden outside local/test/dev")
        if self.reranker_provider_enabled:
            if (
                not self.reranker_provider_base_url
                or not self.reranker_provider_base_url.startswith("https://")
            ):
                raise ValueError("QA_RERANKER_PROVIDER_BASE_URL must be an https URL")
            if not self.reranker_provider_api_key or not self.reranker_provider_model:
                raise ValueError("reranker provider key and model are required")
        if self.app_env in {"staging", "production"} and self.rag_enabled:
            if not self.reranker_provider_enabled:
                raise ValueError("an approved reranker provider is required for production RAG")
            if not self.database_url.startswith("postgresql"):
                raise ValueError("production RAG requires PostgreSQL with pgvector")
        if not 0.1 <= self.reranker_timeout_seconds <= 120:
            raise ValueError("QA_RERANKER_TIMEOUT_SECONDS must be between 0.1 and 120")
        if self.app_env in {"staging", "production"} and self.local_governance_evaluator_enabled:
            raise ValueError("the local governance evaluator is forbidden outside development")
        return self
