from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
