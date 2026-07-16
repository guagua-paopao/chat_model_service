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
    status: Literal[
        "awaiting_upload", "queued", "processing", "published", "failed", "archived"
    ]
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
