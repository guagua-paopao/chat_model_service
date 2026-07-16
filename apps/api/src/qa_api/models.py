from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(StrictModel):
    status: Literal["ready"] = "ready"
    checks: dict[str, str]


class TenantSummary(StrictModel):
    id: UUID
    code: str


class MeResponse(StrictModel):
    id: UUID
    tenant: TenantSummary
    roles: list[str]
    groups: list[str]
    permissions: list[str]
    display_name: str
    locale: str


class ConversationCreate(StrictModel):
    title: str = Field(default="新对话", min_length=1, max_length=300)
    knowledge_base_ids: list[UUID] = Field(default_factory=list, max_length=10)
    channel: Literal["web", "api", "approved_connector"]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("knowledge_base_ids")
    @classmethod
    def unique_knowledge_bases(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("knowledge_base_ids must be unique")
        return value

    @field_validator("metadata")
    @classmethod
    def metadata_is_bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 20:
            raise ValueError("metadata may contain at most 20 properties")
        return value


class ConversationPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    status: Literal["active", "archived"] | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    @model_validator(mode="after")
    def at_least_one_change(self) -> ConversationPatch:
        if self.title is None and self.status is None:
            raise ValueError("at least one field must be supplied")
        return self


class ConversationResponse(StrictModel):
    id: UUID
    title: str
    status: Literal["active", "archived"]
    channel: Literal["web", "api", "approved_connector"]
    knowledge_base_ids: list[UUID]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(StrictModel):
    items: list[ConversationResponse]
    next_cursor: str | None = None


class CitationResponse(StrictModel):
    id: UUID
    ordinal: int = Field(ge=1)
    source_id: str
    document_id: UUID
    document_version_id: UUID
    document_title: str
    version: int = Field(ge=1)
    page_from: int | None = Field(default=None, ge=1)
    page_to: int | None = Field(default=None, ge=1)
    section_path: list[str] = Field(default_factory=list)
    quote: str
    relevance_score: float = Field(ge=0, le=1)


class CitationDetailResponse(CitationResponse):
    message_id: UUID
    access_checked_at: datetime
    source_url: None = None


class MessageResponse(StrictModel):
    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant"]
    content: str
    content_format: Literal["text", "markdown", "json"] = "markdown"
    status: Literal["pending", "streaming", "completed", "failed", "cancelled", "blocked"]
    sequence_no: int
    finish_reason: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    provider: str | None = None
    model: str | None = None
    error_code: str | None = None
    response_mode: Literal["general", "grounded_answer", "search_only"] = "general"
    knowledge_base_ids: list[UUID] = Field(default_factory=list)
    retrieval_run_id: UUID | None = None
    prompt_version: str | None = None
    abstention_reason: str | None = None
    citations: list[CitationResponse] = Field(default_factory=list)


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse] = Field(default_factory=list)
    next_cursor: str | None = None


class ChatClientContext(StrictModel):
    locale: str | None = Field(default=None, min_length=2, max_length=16)


class ChatCompletionRequest(StrictModel):
    conversation_id: UUID
    message: str = Field(min_length=1, max_length=8_000)
    knowledge_base_ids: list[UUID] = Field(default_factory=list, max_length=10)
    stream: bool
    model_policy: Literal["fast", "balanced", "quality"] = "balanced"
    response_mode: Literal["general", "grounded_answer", "search_only"] = "general"
    client_context: ChatClientContext = Field(default_factory=ChatClientContext)

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value

    @field_validator("knowledge_base_ids")
    @classmethod
    def unique_knowledge_bases(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("knowledge_base_ids must be unique")
        return value


class UsageResponse(StrictModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    estimated: bool
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class ChatCompletionResponse(StrictModel):
    request_id: str
    message: MessageResponse
    citations: list[CitationResponse] = Field(default_factory=list)
    usage: UsageResponse


class CancellationResponse(StrictModel):
    message_id: UUID
    status: Literal["cancelling", "cancelled"]


class RetryRequest(StrictModel):
    stream: bool = True
    model_policy: Literal["fast", "balanced", "quality"] = "balanced"


class FeedbackRequest(StrictModel):
    rating: Literal[-1, 1]
    reason_code: Literal[
        "helpful",
        "incorrect",
        "factually_unsupported",
        "incorrect_citation",
        "outdated",
        "unsafe",
        "other",
    ]
    comment: str | None = Field(default=None, max_length=2_000)


class FeedbackResponse(FeedbackRequest):
    id: UUID
    message_id: UUID
    snapshot: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ModelSummary(StrictModel):
    id: str
    display_name: str
    capabilities: list[str]
    status: Literal["available", "degraded"]
    max_context_tokens: int
    allowed_policies: list[Literal["fast", "balanced", "quality"]]


class ModelListResponse(StrictModel):
    items: list[ModelSummary]


Classification = Literal["public", "internal", "confidential", "restricted"]


class KnowledgeBaseCreate(StrictModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    classification: Classification = "internal"

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class KnowledgeBaseResponse(StrictModel):
    id: UUID
    code: str
    name: str
    description: str | None
    classification: Classification
    status: Literal["active", "archived"]
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseListResponse(StrictModel):
    items: list[KnowledgeBaseResponse]


class DocumentAclEntry(StrictModel):
    subject_type: Literal["user", "group", "role"]
    subject_id: str = Field(min_length=1, max_length=128)
    permission: Literal["read"] = "read"

    @field_validator("subject_id")
    @classmethod
    def subject_id_is_safe(cls, value: str) -> str:
        value = value.strip()
        if not value or any(character.isspace() for character in value):
            raise ValueError("subject_id must be a non-blank identifier without whitespace")
        return value


class DocumentCreate(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    filename: str = Field(min_length=1, max_length=255)
    mime_type: Literal[
        "text/plain",
        "text/markdown",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    size_bytes: int = Field(ge=1, le=104_857_600)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    classification: Classification
    acl: list[DocumentAclEntry] = Field(min_length=1, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "filename")
    @classmethod
    def text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("filename")
    @classmethod
    def filename_is_not_a_path(cls, value: str) -> str:
        if "/" in value or "\\" in value or any(ord(character) < 32 for character in value):
            raise ValueError("filename must not contain path separators or control characters")
        return value

    @field_validator("acl")
    @classmethod
    def acl_is_unique(cls, value: list[DocumentAclEntry]) -> list[DocumentAclEntry]:
        keys = {(item.subject_type, item.subject_id, item.permission) for item in value}
        if len(keys) != len(value):
            raise ValueError("acl entries must be unique")
        return value

    @field_validator("metadata")
    @classmethod
    def metadata_is_bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 20:
            raise ValueError("metadata may contain at most 20 properties")
        return value


class DocumentVersionCreate(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    mime_type: Literal[
        "text/plain",
        "text/markdown",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    size_bytes: int = Field(ge=1, le=104_857_600)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("filename")
    @classmethod
    def filename_is_safe(cls, value: str) -> str:
        value = value.strip()
        if (
            not value
            or "/" in value
            or "\\" in value
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("filename must be a name, not a path")
        return value


class DocumentVersionResponse(StrictModel):
    id: UUID
    version_no: int
    filename: str
    declared_mime_type: str
    detected_mime_type: str | None
    declared_size_bytes: int
    actual_size_bytes: int | None
    declared_sha256: str
    actual_sha256: str | None
    status: Literal["awaiting_upload", "queued", "processing", "published", "failed", "archived"]
    parser_version: str | None
    chunker_version: str | None
    embedding_model: str | None
    page_count: int | None
    chunk_count: int | None
    token_count: int | None
    created_at: datetime
    published_at: datetime | None


class DocumentUploadResponse(StrictModel):
    document_id: UUID
    version: DocumentVersionResponse
    upload_url: str
    upload_method: Literal["PUT"] = "PUT"
    upload_headers: dict[str, str]
    upload_expires_at: datetime


class UploadReceiptResponse(StrictModel):
    version_id: UUID
    status: Literal["uploaded"] = "uploaded"


class UploadCompleteRequest(StrictModel):
    version_id: UUID
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class IngestionJobResponse(StrictModel):
    id: UUID
    document_id: UUID
    version_id: UUID
    status: Literal["queued", "running", "completed", "failed", "dead_letter"]
    stage: Literal[
        "queued", "scanning", "parsing", "chunking", "embedding", "publishing", "completed"
    ]
    progress: int = Field(ge=0, le=100)
    attempt: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    metrics: dict[str, Any]
    error_code: str | None
    error_detail: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class DocumentDetailResponse(StrictModel):
    id: UUID
    knowledge_base_id: UUID
    title: str
    classification: Classification
    status: Literal["awaiting_upload", "processing", "ready", "failed", "archived"]
    current_version_id: UUID | None
    metadata: dict[str, Any]
    acl: list[DocumentAclEntry]
    versions: list[DocumentVersionResponse]
    latest_job: IngestionJobResponse | None
    created_at: datetime
    updated_at: datetime


class RetrievalSearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=1000)
    kb_ids: list[UUID] = Field(min_length=1, max_length=10)
    top_k: int = Field(default=5, ge=1, le=20)
    include_content: bool = False
    filters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value

    @field_validator("kb_ids")
    @classmethod
    def kb_ids_are_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("kb_ids must be unique")
        return value


class RetrievalSearchHit(StrictModel):
    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_title: str
    score: float
    page_from: int | None
    page_to: int | None
    section_path: list[str]
    content: str | None


class RetrievalSearchResponse(StrictModel):
    items: list[RetrievalSearchHit]
    total_candidates: int
    acl_filtered: bool = True
    stage: Literal["debug_only_not_connected_to_chat"] = "debug_only_not_connected_to_chat"


class Problem(StrictModel):
    type: str
    title: str
    status: int
    code: str
    detail: str
    instance: str | None = None
    request_id: str
    retryable: bool = False
    errors: list[dict[str, str]] | None = None


class AdminUserResponse(StrictModel):
    id: UUID
    subject: str
    email: str | None
    display_name: str
    status: Literal["active", "disabled"]
    roles: list[str]
    groups: list[str]
    version: int = Field(ge=1)
    identity_synced_at: datetime | None
    disabled_at: datetime | None
    updated_at: datetime


class AdminUserListResponse(StrictModel):
    items: list[AdminUserResponse]


class AdminUserPatch(StrictModel):
    status: Literal["active", "disabled"]
    reason: str = Field(min_length=10, max_length=500)
    approval_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class AdminGroupResponse(StrictModel):
    id: UUID
    code: str
    display_name: str
    external_id: str | None
    status: Literal["active", "disabled"]
    member_count: int = Field(ge=0)
    version: int = Field(ge=1)
    identity_synced_at: datetime | None
    updated_at: datetime


class AdminGroupListResponse(StrictModel):
    items: list[AdminGroupResponse]


class RagConfigDraftCreate(StrictModel):
    prompt_version: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    prompt_template: str = Field(min_length=100, max_length=20_000)
    config: dict[str, Any]
    reason: str = Field(min_length=10, max_length=500)


class RagConfigEvaluationResponse(StrictModel):
    id: UUID
    rag_config_id: UUID
    dataset_version: str
    dataset_checksum: str
    evaluator_version: str
    status: Literal["completed"]
    gate_result: Literal["passed", "failed"]
    metrics: dict[str, Any]
    thresholds: dict[str, Any]
    failed_checks: list[str]
    created_by: UUID
    created_at: datetime
    completed_at: datetime | None


class RagConfigResponse(StrictModel):
    id: UUID
    code: str
    version: int = Field(ge=1)
    status: Literal["draft", "evaluated", "approved", "published", "archived"]
    prompt_version: str
    config: dict[str, Any]
    checksum: str
    evaluation_status: Literal["pending", "passed", "failed"]
    change_reason: str
    supersedes_id: UUID | None
    rollback_of_id: UUID | None
    created_by: UUID
    created_at: datetime
    approved_by: UUID | None
    approved_at: datetime | None
    approval_id: str | None
    published_by: UUID | None
    published_at: datetime | None


class RagConfigListResponse(StrictModel):
    items: list[RagConfigResponse]


class GovernanceActionRequest(StrictModel):
    reason: str = Field(min_length=10, max_length=500)
    approval_id: str | None = Field(
        default=None,
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )


class QuotaPolicyPatch(StrictModel):
    requests_per_minute: int = Field(ge=1, le=10_000)
    concurrent_requests: int = Field(ge=1, le=1_000)
    daily_token_limit: int = Field(ge=1_000, le=1_000_000_000)
    monthly_cost_limit: Decimal = Field(ge=0, le=10_000_000)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    enabled: bool = True
    reason: str = Field(min_length=10, max_length=500)
    approval_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class QuotaPolicyResponse(StrictModel):
    id: UUID
    scope_type: Literal["tenant", "user"]
    scope_id: str
    requests_per_minute: int
    concurrent_requests: int
    daily_token_limit: int
    monthly_cost_limit: Decimal
    currency: str
    enabled: bool
    version: int
    updated_by: UUID
    updated_at: datetime


class GovernanceAuditResponse(StrictModel):
    id: UUID
    sequence_no: int
    actor_user_id: UUID
    action: str
    resource_type: str
    resource_id: str
    result: str
    reason: str
    approval_id: str | None
    request_id: str
    trace_id: str | None
    details_safe: dict[str, Any]
    previous_hash: str
    event_hash: str
    occurred_at: datetime


class GovernanceAuditListResponse(StrictModel):
    items: list[GovernanceAuditResponse]
    next_sequence: int | None = None


class AuditIntegrityResponse(StrictModel):
    valid: bool
    checked_events: int
    first_invalid_sequence: int | None = None


class UsageSummaryResponse(StrictModel):
    from_time: datetime
    to_time: datetime
    requests: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    amount: Decimal
    currency: str


class QualitySummaryResponse(StrictModel):
    from_time: datetime
    to_time: datetime
    retrieval_runs: int
    abstentions: int
    abstention_rate: float
    citations: int
    positive_feedback: int
    negative_feedback: int


class SecurityIncidentCreate(StrictModel):
    title: str = Field(min_length=5, max_length=300)
    category: Literal[
        "prompt_injection",
        "data_exposure",
        "access_control",
        "credential_exposure",
        "abuse",
        "other",
    ]
    severity: Literal["P0", "P1", "P2", "P3"]
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    owner_user_id: UUID
    reason: str = Field(min_length=10, max_length=500)


class SecurityIncidentPatch(StrictModel):
    status: Literal["triaged", "contained", "resolved", "closed"]
    resolution_safe: str | None = Field(default=None, max_length=1000)
    reason: str = Field(min_length=10, max_length=500)
    approval_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class SecurityIncidentResponse(StrictModel):
    id: UUID
    title: str
    category: str
    severity: Literal["P0", "P1", "P2", "P3"]
    status: Literal["open", "triaged", "contained", "resolved", "closed"]
    evidence_refs: list[str]
    owner_user_id: UUID
    resolution_safe: str | None
    version: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class SecurityIncidentListResponse(StrictModel):
    items: list[SecurityIncidentResponse]


class EvaluationRunCreate(StrictModel):
    dataset_version_id: str = Field(default="s6-mini-golden-v1", min_length=1, max_length=128)
    candidate_config_ids: list[UUID] = Field(min_length=1, max_length=5)
    baseline_run_id: UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("candidate_config_ids")
    @classmethod
    def candidate_ids_are_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("candidate_config_ids must be unique")
        return value

    @field_validator("tags")
    @classmethod
    def tags_are_safe(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip().lower() for item in value]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("tags must be unique")
        if any(not item or len(item) > 32 for item in cleaned):
            raise ValueError("tags must contain 1 to 32 characters")
        if any(not item.replace("-", "").replace("_", "").isalnum() for item in cleaned):
            raise ValueError("tags may contain letters, numbers, hyphens and underscores")
        return cleaned


class EvaluationRunResponse(StrictModel):
    id: UUID
    dataset_version_id: str
    dataset_checksum: str
    candidate_config_ids: list[UUID]
    baseline_run_id: UUID | None
    status: Literal["completed", "failed"]
    metrics: dict[str, Any]
    thresholds: dict[str, Any]
    deltas: dict[str, Any]
    gate_result: Literal["passed", "failed"]
    failed_cases: list[dict[str, Any]]
    amount: Decimal
    currency: str
    code_revision: str
    evaluator_version: str
    tags: list[str]
    error_code: str | None
    created_by: UUID
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime


class EvaluationRunListResponse(StrictModel):
    items: list[EvaluationRunResponse]


class UsageBreakdown(StrictModel):
    key: str
    requests: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    amount: Decimal
    currency: str


class UsageReportResponse(StrictModel):
    from_time: datetime
    to_time: datetime
    group_by: Literal["none", "model", "operation"]
    items: list[UsageBreakdown]


class OperationsSnapshotResponse(StrictModel):
    generated_at: datetime
    scope: Literal["process_and_tenant_snapshot"]
    production_slo_evidence: Literal[False]
    request_window: dict[str, Any]
    tenant_signals: dict[str, Any]


class ReleaseCandidateCreate(StrictModel):
    release_version: str = Field(
        min_length=3, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$"
    )
    git_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    sbom_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    db_migration: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    model_route_versions: list[str] = Field(min_length=1, max_length=10)
    eval_run_id: UUID
    rollback_target: str = Field(
        min_length=3, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$"
    )
    known_issues: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("model_route_versions")
    @classmethod
    def route_versions_are_unique_and_safe(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if len(set(cleaned)) != len(cleaned) or any(
            not item or len(item) > 128 for item in cleaned
        ):
            raise ValueError(
                "model_route_versions must be unique non-empty values up to 128 characters"
            )
        return cleaned

    @field_validator("known_issues")
    @classmethod
    def known_issues_are_safe(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item or len(item) > 300 for item in cleaned):
            raise ValueError("known_issues must contain safe summaries up to 300 characters")
        return cleaned


class ReleaseUatResultCreate(StrictModel):
    case_id: Literal["UC-01", "UC-02", "UC-03", "UC-04", "UC-05"]
    result: Literal["passed", "failed"]
    evidence_ref: str = Field(
        min_length=3, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]+$"
    )
    notes_safe: str | None = Field(default=None, max_length=500)


class ReleaseSignoffCreate(StrictModel):
    category: Literal["product", "business", "data", "security", "sre"]
    decision: Literal["approved", "rejected"]
    approval_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    evidence_ref: str = Field(
        min_length=3, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]+$"
    )
    reason: str = Field(min_length=10, max_length=500)


class RolloutObservation(StrictModel):
    observed_seconds: int = Field(ge=60, le=86_400)
    requests: int = Field(ge=1, le=100_000_000)
    server_error_rate: float = Field(ge=0, le=1)
    ttft_p95_ms: float = Field(ge=0, le=600_000)
    response_p95_ms: float = Field(ge=0, le=600_000)
    negative_feedback_rate: float = Field(ge=0, le=1)
    citation_precision: float = Field(ge=0, le=1)
    cost_delta_ratio: float = Field(ge=-1, le=10)
    quality_delta: float = Field(ge=-1, le=1)
    security_incidents: int = Field(ge=0, le=1_000_000)
    unauthorized_leakage_count: int = Field(ge=0, le=1_000_000)
    evidence_ref: str = Field(
        min_length=3, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]+$"
    )


class ReleaseRolloutAdvance(StrictModel):
    target_stage: Literal["percent_5", "percent_25", "percent_50", "percent_100"]
    observation: RolloutObservation
    reason: str = Field(min_length=10, max_length=500)


class ReleaseActionRequest(StrictModel):
    reason: str = Field(min_length=10, max_length=500)
    approval_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class ReleaseUatResultResponse(StrictModel):
    case_id: str
    result: Literal["passed", "failed"]
    evidence_ref: str
    notes_safe: str | None
    executed_by: UUID
    executed_at: datetime


class ReleaseSignoffResponse(StrictModel):
    category: str
    decision: Literal["approved", "rejected"]
    approval_id: str
    evidence_ref: str
    reason: str
    signed_by: UUID
    signed_at: datetime


class ReleaseRolloutEventResponse(StrictModel):
    sequence_no: int
    action: str
    from_stage: str
    to_stage: str
    decision: str
    observation: dict[str, Any]
    reason: str
    actor_user_id: UUID
    event_hash: str
    occurred_at: datetime


class ReleaseCandidateResponse(StrictModel):
    id: UUID
    release_version: str
    git_sha: str
    image_digest: str
    sbom_digest: str
    db_migration: str
    prompt_versions: list[str]
    retrieval_versions: list[str]
    model_route_versions: list[str]
    dataset_version: str
    eval_run_id: UUID
    rollback_target: str
    known_issues: list[str]
    artifact_checksum: str
    status: Literal[
        "draft",
        "qualified",
        "approved",
        "rolling_out",
        "stopped",
        "rejected",
        "completed",
        "rolled_back",
    ]
    current_stage: Literal[
        "none", "dark", "percent_5", "percent_25", "percent_50", "percent_100", "rolled_back"
    ]
    uat_results: list[ReleaseUatResultResponse]
    signoffs: list[ReleaseSignoffResponse]
    rollout_events: list[ReleaseRolloutEventResponse]
    rollout_integrity_valid: bool
    created_by: UUID
    created_at: datetime
    qualified_at: datetime | None
    approved_at: datetime | None
    completed_at: datetime | None


class ReleaseCandidateListResponse(StrictModel):
    items: list[ReleaseCandidateResponse]
