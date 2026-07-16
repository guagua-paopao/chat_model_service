from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    tenant_id: UUID
    tenant_code: str
    subject: str
    display_name: str
    locale: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConversationRecord:
    id: UUID
    tenant_id: UUID
    user_id: UUID
    title: str
    status: str
    channel: str
    knowledge_base_ids: tuple[UUID, ...]
    metadata: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MessageRecord:
    id: UUID
    tenant_id: UUID
    conversation_id: UUID
    role: str
    content: str
    content_format: str
    status: str
    sequence_no: int
    parent_message_id: UUID | None
    request_id: str | None
    finish_reason: str | None
    provider_code: str | None
    model_code: str | None
    route_code: str | None
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    error_code: str | None
    response_mode: str
    knowledge_base_ids: tuple[UUID, ...]
    rag_config_id: UUID | None
    retrieval_run_id: UUID | None
    prompt_version: str | None
    abstention_reason: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class UsageRecord:
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    estimated: bool
    amount: Decimal
    currency: str


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.retryable = retryable
