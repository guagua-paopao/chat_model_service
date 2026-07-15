from __future__ import annotations

from datetime import datetime
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


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse] = Field(default_factory=list)
    next_cursor: str | None = None


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
