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
    citations: list[dict[str, Any]] = Field(default_factory=list)
    usage: UsageResponse


class CancellationResponse(StrictModel):
    message_id: UUID
    status: Literal["cancelling", "cancelled"]


class RetryRequest(StrictModel):
    stream: bool = True
    model_policy: Literal["fast", "balanced", "quality"] = "balanced"


class ModelSummary(StrictModel):
    id: str
    display_name: str
    capabilities: list[str]
    status: Literal["available", "degraded"]
    max_context_tokens: int
    allowed_policies: list[Literal["fast", "balanced", "quality"]]


class ModelListResponse(StrictModel):
    items: list[ModelSummary]


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
