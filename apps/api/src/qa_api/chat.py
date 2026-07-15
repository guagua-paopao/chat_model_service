from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from qa_api.config import Settings
from qa_api.domain import ApiError, MessageRecord, Principal
from qa_api.ids import uuid7
from qa_api.model_gateway import (
    AttemptReport,
    GatewayUsage,
    ModelCancelled,
    ModelGateway,
    ModelProviderError,
    ModelRoute,
    estimate_tokens,
)
from qa_api.persistence import (
    AuditLogRow,
    ConversationRow,
    MessageRow,
    ModelInvocationRow,
    UsageLedgerRow,
    utc_now,
)


@dataclass(slots=True)
class QuotaLease:
    tenant_semaphore: asyncio.Semaphore
    user_semaphore: asyncio.Semaphore
    released: bool = False

    def release(self) -> None:
        if self.released:
            return
        self.user_semaphore.release()
        self.tenant_semaphore.release()
        self.released = True


class QuotaManager:
    """Single-process S2/S3 guard; production replaces counters with Redis atomics."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = asyncio.Lock()
        self._requests: dict[tuple[UUID, UUID], deque[float]] = defaultdict(deque)
        self._tenant_slots: dict[UUID, asyncio.Semaphore] = {}
        self._user_slots: dict[tuple[UUID, UUID], asyncio.Semaphore] = {}

    async def acquire(self, *, tenant_id: UUID, user_id: UUID, prompt: str) -> QuotaLease:
        estimated = estimate_tokens(prompt)
        if estimated > self._settings.chat_max_input_tokens:
            raise ApiError(
                413,
                "CHAT_INPUT_TOO_LARGE",
                "Input too large",
                "The message exceeds the configured input token budget.",
            )
        now = time.monotonic()
        async with self._lock:
            key = (tenant_id, user_id)
            window = self._requests[key]
            while window and now - window[0] >= 60:
                window.popleft()
            if len(window) >= self._settings.chat_requests_per_minute:
                raise ApiError(
                    429,
                    "CHAT_RATE_LIMITED",
                    "Too many requests",
                    "The chat request rate limit was exceeded.",
                    retryable=True,
                )
            window.append(now)
            tenant_slot = self._tenant_slots.setdefault(
                tenant_id, asyncio.Semaphore(self._settings.chat_tenant_concurrency)
            )
            user_slot = self._user_slots.setdefault(
                key, asyncio.Semaphore(self._settings.chat_user_concurrency)
            )
        try:
            await asyncio.wait_for(tenant_slot.acquire(), timeout=0.05)
        except TimeoutError as exc:
            raise ApiError(
                429,
                "TENANT_CONCURRENCY_EXCEEDED",
                "Too many requests",
                "The tenant chat concurrency limit was exceeded.",
                retryable=True,
            ) from exc
        try:
            await asyncio.wait_for(user_slot.acquire(), timeout=0.05)
        except TimeoutError as exc:
            tenant_slot.release()
            raise ApiError(
                429,
                "USER_CONCURRENCY_EXCEEDED",
                "Too many requests",
                "The user chat concurrency limit was exceeded.",
                retryable=True,
            ) from exc
        return QuotaLease(tenant_slot, user_slot)


class CancellationRegistry:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._events: dict[UUID, asyncio.Event] = {}

    async def register(self, message_id: UUID) -> asyncio.Event:
        event = asyncio.Event()
        async with self._lock:
            self._events[message_id] = event
        return event

    async def cancel(self, message_id: UUID) -> bool:
        async with self._lock:
            event = self._events.get(message_id)
            if event is None:
                return False
            event.set()
            return True

    async def unregister(self, message_id: UUID) -> None:
        async with self._lock:
            self._events.pop(message_id, None)


@dataclass(frozen=True, slots=True)
class PreparedChat:
    tenant_id: UUID
    user_id: UUID
    conversation_id: UUID
    assistant_message_id: UUID
    prompt: str
    locale: str
    policy: str
    request_id: str
    trace_id: str
    lease: QuotaLease


@dataclass(frozen=True, slots=True)
class ChatEvent:
    event: str
    data: dict[str, Any]


class ChatRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def begin_new(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        request_id: str,
        trace_id: str,
    ) -> MessageRecord:
        conversation = self._conversation(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id, for_update=True
        )
        next_sequence = self._next_sequence(tenant_id, conversation_id)
        user_message = MessageRow(
            id=uuid7(),
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            role="user",
            content=content,
            content_format="text",
            status="completed",
            sequence_no=next_sequence,
            request_id=request_id,
            finish_reason="stop",
            completed_at=utc_now(),
        )
        assistant = MessageRow(
            id=uuid7(),
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            role="assistant",
            content="",
            content_format="markdown",
            status="pending",
            sequence_no=next_sequence + 1,
            parent_message_id=user_message.id,
            request_id=request_id,
        )
        conversation.updated_at = utc_now()
        self._session.add_all([user_message, assistant])
        self._audit(
            tenant_id=tenant_id,
            user_id=user_id,
            action="chat.start",
            resource_id=str(assistant.id),
            request_id=request_id,
            trace_id=trace_id,
            details={"conversation_id": str(conversation_id)},
        )
        self._session.commit()
        self._session.refresh(assistant)
        return _message_record(assistant)

    def begin_retry(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        failed_message_id: UUID,
        request_id: str,
        trace_id: str,
    ) -> tuple[MessageRecord, str]:
        failed = self._scoped_assistant(
            tenant_id=tenant_id, user_id=user_id, message_id=failed_message_id
        )
        if failed.status not in {"failed", "cancelled"} or failed.parent_message_id is None:
            raise ApiError(
                409,
                "MESSAGE_NOT_RETRYABLE",
                "Conflict",
                "Only failed or cancelled assistant messages can be retried.",
            )
        parent = self._session.scalar(
            select(MessageRow).where(
                MessageRow.tenant_id == tenant_id,
                MessageRow.id == failed.parent_message_id,
                MessageRow.role == "user",
            )
        )
        if parent is None:
            raise ApiError(409, "MESSAGE_PARENT_MISSING", "Conflict", "Retry context is missing.")
        self._conversation(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=failed.conversation_id,
            for_update=True,
        )
        assistant = MessageRow(
            id=uuid7(),
            tenant_id=tenant_id,
            conversation_id=failed.conversation_id,
            role="assistant",
            content="",
            content_format="markdown",
            status="pending",
            sequence_no=self._next_sequence(tenant_id, failed.conversation_id),
            parent_message_id=parent.id,
            request_id=request_id,
        )
        self._session.add(assistant)
        self._audit(
            tenant_id=tenant_id,
            user_id=user_id,
            action="chat.retry",
            resource_id=str(assistant.id),
            request_id=request_id,
            trace_id=trace_id,
            details={"retried_message_id": str(failed_message_id)},
        )
        self._session.commit()
        self._session.refresh(assistant)
        return _message_record(assistant), parent.content

    def list_messages(
        self, *, tenant_id: UUID, user_id: UUID, conversation_id: UUID
    ) -> list[MessageRecord]:
        self._conversation(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        rows = self._session.scalars(
            select(MessageRow)
            .where(
                MessageRow.tenant_id == tenant_id,
                MessageRow.conversation_id == conversation_id,
            )
            .order_by(MessageRow.sequence_no)
        )
        return [_message_record(row) for row in rows]

    def mark_streaming(self, *, tenant_id: UUID, message_id: UUID) -> None:
        self._session.execute(
            update(MessageRow)
            .where(
                MessageRow.tenant_id == tenant_id,
                MessageRow.id == message_id,
                MessageRow.status == "pending",
            )
            .values(status="streaming", updated_at=utc_now())
        )
        self._session.commit()

    def record_attempt(
        self,
        *,
        prepared: PreparedChat,
        report: AttemptReport,
    ) -> None:
        if report.status == "started":
            self._session.add(
                ModelInvocationRow(
                    id=uuid7(),
                    tenant_id=prepared.tenant_id,
                    user_id=prepared.user_id,
                    conversation_id=prepared.conversation_id,
                    message_id=prepared.assistant_message_id,
                    request_id=prepared.request_id,
                    trace_id=prepared.trace_id,
                    attempt_no=report.attempt_no,
                    route_code=report.route.code,
                    route_version=report.route.version,
                    provider_code=report.route.provider_code,
                    model_code=report.route.model_code,
                    status="started",
                    retryable=False,
                )
            )
        else:
            self._session.execute(
                update(ModelInvocationRow)
                .where(
                    ModelInvocationRow.tenant_id == prepared.tenant_id,
                    ModelInvocationRow.request_id == prepared.request_id,
                    ModelInvocationRow.attempt_no == report.attempt_no,
                )
                .values(
                    status=report.status,
                    error_code=report.error_code,
                    retryable=report.retryable,
                    latency_ms=report.latency_ms,
                    ttft_ms=report.ttft_ms,
                    completed_at=utc_now(),
                )
            )
        self._session.commit()

    def complete(
        self,
        *,
        prepared: PreparedChat,
        content: str,
        route: ModelRoute,
        usage: GatewayUsage,
        finish_reason: str,
    ) -> MessageRecord:
        now = utc_now()
        self._session.execute(
            update(MessageRow)
            .where(
                MessageRow.tenant_id == prepared.tenant_id,
                MessageRow.id == prepared.assistant_message_id,
                MessageRow.status.in_(["pending", "streaming"]),
            )
            .values(
                content=content,
                status="completed",
                finish_reason=finish_reason,
                provider_code=route.provider_code,
                model_code=route.model_code,
                route_code=route.code,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_tokens=usage.cached_tokens,
                updated_at=now,
                completed_at=now,
            )
        )
        self._session.add(
            UsageLedgerRow(
                id=uuid7(),
                tenant_id=prepared.tenant_id,
                user_id=prepared.user_id,
                conversation_id=prepared.conversation_id,
                message_id=prepared.assistant_message_id,
                request_id=prepared.request_id,
                provider_code=route.provider_code,
                model_code=route.model_code,
                route_code=route.code,
                route_version=route.version,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_tokens=usage.cached_tokens,
                estimated=usage.estimated,
                amount=usage.amount,
                currency=usage.currency,
                price_snapshot=usage.price_snapshot,
            )
        )
        self._audit(
            tenant_id=prepared.tenant_id,
            user_id=prepared.user_id,
            action="chat.complete",
            resource_id=str(prepared.assistant_message_id),
            request_id=prepared.request_id,
            trace_id=prepared.trace_id,
            details={"route": route.code, "finish_reason": finish_reason},
        )
        self._session.commit()
        return self.get_message(
            tenant_id=prepared.tenant_id,
            user_id=prepared.user_id,
            message_id=prepared.assistant_message_id,
        )

    def fail(self, *, prepared: PreparedChat, error: ModelProviderError) -> None:
        now = utc_now()
        self._session.execute(
            update(MessageRow)
            .where(
                MessageRow.tenant_id == prepared.tenant_id,
                MessageRow.id == prepared.assistant_message_id,
                MessageRow.status.in_(["pending", "streaming"]),
            )
            .values(
                status="failed",
                finish_reason="error",
                error_code=error.code,
                error_detail_safe=error.safe_message,
                updated_at=now,
                completed_at=now,
            )
        )
        self._audit(
            tenant_id=prepared.tenant_id,
            user_id=prepared.user_id,
            action="chat.fail",
            resource_id=str(prepared.assistant_message_id),
            request_id=prepared.request_id,
            trace_id=prepared.trace_id,
            details={"error_code": error.code, "retryable": error.retryable},
        )
        self._session.commit()

    def cancel(self, *, prepared: PreparedChat) -> None:
        self._mark_cancelled(
            tenant_id=prepared.tenant_id,
            user_id=prepared.user_id,
            message_id=prepared.assistant_message_id,
            request_id=prepared.request_id,
            trace_id=prepared.trace_id,
        )

    def cancel_without_active_stream(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        message_id: UUID,
        request_id: str,
        trace_id: str,
    ) -> str:
        row = self._scoped_assistant(
            tenant_id=tenant_id, user_id=user_id, message_id=message_id
        )
        if row.status == "cancelled":
            return "cancelled"
        if row.status not in {"pending", "streaming"}:
            raise ApiError(
                409,
                "MESSAGE_NOT_CANCELLABLE",
                "Conflict",
                "Only pending or streaming messages can be cancelled.",
            )
        self._mark_cancelled(
            tenant_id=tenant_id,
            user_id=user_id,
            message_id=message_id,
            request_id=request_id,
            trace_id=trace_id,
        )
        return "cancelled"

    def get_message(
        self, *, tenant_id: UUID, user_id: UUID, message_id: UUID
    ) -> MessageRecord:
        return _message_record(
            self._scoped_assistant(tenant_id=tenant_id, user_id=user_id, message_id=message_id)
        )

    def recover_orphans(self, *, older_than_seconds: int = 300) -> int:
        cutoff = utc_now() - timedelta(seconds=older_than_seconds)
        result = cast(
            CursorResult[Any],
            self._session.execute(
            update(MessageRow)
            .where(
                MessageRow.status.in_(["pending", "streaming"]),
                MessageRow.updated_at < cutoff,
            )
            .values(
                status="failed",
                finish_reason="error",
                error_code="STREAM_ORPHAN_RECOVERED",
                error_detail_safe="The interrupted stream was recovered during startup.",
                updated_at=utc_now(),
                completed_at=utc_now(),
            )
            ),
        )
        self._session.commit()
        return int(result.rowcount or 0)

    def _conversation(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        conversation_id: UUID,
        for_update: bool = False,
    ) -> ConversationRow:
        statement = select(ConversationRow).where(
            ConversationRow.tenant_id == tenant_id,
            ConversationRow.user_id == user_id,
            ConversationRow.id == conversation_id,
            ConversationRow.status == "active",
            ConversationRow.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        row = self._session.scalar(statement)
        if row is None:
            raise ApiError(
                404,
                "CONVERSATION_NOT_FOUND",
                "Not found",
                "Conversation was not found or is not visible.",
            )
        return row

    def _scoped_assistant(
        self, *, tenant_id: UUID, user_id: UUID, message_id: UUID
    ) -> MessageRow:
        row = self._session.scalar(
            select(MessageRow)
            .join(
                ConversationRow,
                (ConversationRow.tenant_id == MessageRow.tenant_id)
                & (ConversationRow.id == MessageRow.conversation_id),
            )
            .where(
                MessageRow.tenant_id == tenant_id,
                MessageRow.id == message_id,
                MessageRow.role == "assistant",
                ConversationRow.user_id == user_id,
                ConversationRow.deleted_at.is_(None),
            )
        )
        if row is None:
            raise ApiError(
                404,
                "MESSAGE_NOT_FOUND",
                "Not found",
                "Message was not found or is not visible.",
            )
        return row

    def _next_sequence(self, tenant_id: UUID, conversation_id: UUID) -> int:
        current = self._session.scalar(
            select(func.max(MessageRow.sequence_no)).where(
                MessageRow.tenant_id == tenant_id,
                MessageRow.conversation_id == conversation_id,
            )
        )
        return int(current or 0) + 1

    def _mark_cancelled(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        message_id: UUID,
        request_id: str,
        trace_id: str,
    ) -> None:
        now = utc_now()
        self._session.execute(
            update(MessageRow)
            .where(
                MessageRow.tenant_id == tenant_id,
                MessageRow.id == message_id,
                MessageRow.status.in_(["pending", "streaming"]),
            )
            .values(
                status="cancelled",
                finish_reason="cancelled",
                updated_at=now,
                completed_at=now,
            )
        )
        self._audit(
            tenant_id=tenant_id,
            user_id=user_id,
            action="chat.cancel",
            resource_id=str(message_id),
            request_id=request_id,
            trace_id=trace_id,
            details={},
        )
        self._session.commit()

    def _audit(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        action: str,
        resource_id: str,
        request_id: str,
        trace_id: str,
        details: dict[str, object],
    ) -> None:
        self._session.add(
            AuditLogRow(
                id=uuid7(),
                tenant_id=tenant_id,
                actor_user_id=user_id,
                action=action,
                resource_type="message",
                resource_id=resource_id,
                result="success",
                request_id=request_id,
                trace_id=trace_id,
                details_safe=details,
            )
        )


class ChatService:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker[Session],
        gateway: ModelGateway,
        quotas: QuotaManager,
        cancellations: CancellationRegistry,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._gateway = gateway
        self._quotas = quotas
        self._cancellations = cancellations

    def models(self) -> list[ModelRoute]:
        return self._gateway.models()

    def get_message(self, *, principal: Principal, message_id: UUID) -> MessageRecord:
        with self._session_factory() as session:
            return ChatRepository(session).get_message(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                message_id=message_id,
            )

    async def prepare_new(
        self,
        *,
        principal: Principal,
        conversation_id: UUID,
        message: str,
        knowledge_base_ids: list[UUID],
        response_mode: str,
        locale: str,
        policy: str,
        request_id: str,
        trace_id: str,
    ) -> PreparedChat:
        if knowledge_base_ids or response_mode != "general":
            raise ApiError(
                409,
                "KNOWLEDGE_NOT_CONNECTED_IN_S3",
                "Knowledge mode unavailable",
                "S3 retrieval is debug-only and is not connected to chat answers.",
            )
        lease = await self._quotas.acquire(
            tenant_id=principal.tenant_id, user_id=principal.user_id, prompt=message
        )
        try:
            with self._session_factory() as session:
                assistant = ChatRepository(session).begin_new(
                    tenant_id=principal.tenant_id,
                    user_id=principal.user_id,
                    conversation_id=conversation_id,
                    content=message,
                    request_id=request_id,
                    trace_id=trace_id,
                )
        except Exception:
            lease.release()
            raise
        return PreparedChat(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            conversation_id=conversation_id,
            assistant_message_id=assistant.id,
            prompt=message,
            locale=locale,
            policy=policy,
            request_id=request_id,
            trace_id=trace_id,
            lease=lease,
        )

    async def prepare_retry(
        self,
        *,
        principal: Principal,
        failed_message_id: UUID,
        locale: str,
        policy: str,
        request_id: str,
        trace_id: str,
    ) -> PreparedChat:
        with self._session_factory() as session:
            failed = ChatRepository(session).get_message(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                message_id=failed_message_id,
            )
        if failed.parent_message_id is None:
            raise ApiError(409, "MESSAGE_NOT_RETRYABLE", "Conflict", "Retry context is missing.")
        with self._session_factory() as session:
            parent = session.scalar(
                select(MessageRow).where(
                    MessageRow.tenant_id == principal.tenant_id,
                    MessageRow.id == failed.parent_message_id,
                    MessageRow.role == "user",
                )
            )
            if parent is None:
                raise ApiError(
                    409,
                    "MESSAGE_PARENT_MISSING",
                    "Conflict",
                    "Retry context is missing.",
                )
            prompt = parent.content
        lease = await self._quotas.acquire(
            tenant_id=principal.tenant_id, user_id=principal.user_id, prompt=prompt
        )
        try:
            with self._session_factory() as session:
                assistant, prompt = ChatRepository(session).begin_retry(
                    tenant_id=principal.tenant_id,
                    user_id=principal.user_id,
                    failed_message_id=failed_message_id,
                    request_id=request_id,
                    trace_id=trace_id,
                )
        except Exception:
            lease.release()
            raise
        return PreparedChat(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            conversation_id=assistant.conversation_id,
            assistant_message_id=assistant.id,
            prompt=prompt,
            locale=locale,
            policy=policy,
            request_id=request_id,
            trace_id=trace_id,
            lease=lease,
        )

    async def execute(self, prepared: PreparedChat) -> AsyncGenerator[ChatEvent, None]:
        cancellation = await self._cancellations.register(prepared.assistant_message_id)
        sequence = 1
        content_parts: list[str] = []
        usage: GatewayUsage | None = None
        route: ModelRoute | None = None
        with self._session_factory() as session:
            ChatRepository(session).mark_streaming(
                tenant_id=prepared.tenant_id, message_id=prepared.assistant_message_id
            )
        yield self._event(
            prepared,
            sequence,
            "message.started",
            {"model_policy": prepared.policy},
        )
        sequence += 1
        try:
            async for event in self._gateway.stream(
                prompt=prepared.prompt,
                locale=prepared.locale,
                policy=prepared.policy,
                cancellation=cancellation,
            ):
                if event.kind == "attempt" and event.attempt:
                    with self._session_factory() as session:
                        ChatRepository(session).record_attempt(
                            prepared=prepared, report=event.attempt
                        )
                elif event.kind == "delta" and event.delta:
                    content_parts.append(event.delta)
                    route = event.route or route
                    yield self._event(
                        prepared, sequence, "message.delta", {"delta": event.delta}
                    )
                    sequence += 1
                elif event.kind == "usage" and event.usage:
                    usage = event.usage
                    route = event.route or route
                    yield self._event(
                        prepared,
                        sequence,
                        "usage",
                        {
                            "input_tokens": usage.input_tokens,
                            "output_tokens": usage.output_tokens,
                            "cached_tokens": usage.cached_tokens,
                            "estimated": usage.estimated,
                            "amount": str(usage.amount),
                            "currency": usage.currency,
                        },
                    )
                    sequence += 1
                elif event.kind == "completed":
                    route = event.route or route
                    if route is None or usage is None:
                        raise ModelProviderError(
                            "MODEL_PROTOCOL_ERROR",
                            "The model gateway did not return completion metadata.",
                            retryable=False,
                        )
                    finish_reason = event.finish_reason or "stop"
                    with self._session_factory() as session:
                        ChatRepository(session).complete(
                            prepared=prepared,
                            content="".join(content_parts),
                            route=route,
                            usage=usage,
                            finish_reason=finish_reason,
                        )
                    yield self._event(
                        prepared,
                        sequence,
                        "message.completed",
                        {
                            "finish_reason": finish_reason,
                            "trace_id": prepared.trace_id,
                            "provider": route.provider_code,
                            "model": route.model_code,
                        },
                    )
                    return
        except ModelCancelled:
            with self._session_factory() as session:
                ChatRepository(session).cancel(prepared=prepared)
            yield self._event(
                prepared,
                sequence,
                "message.completed",
                {"finish_reason": "cancelled", "trace_id": prepared.trace_id},
            )
        except asyncio.CancelledError:
            with self._session_factory() as session:
                ChatRepository(session).cancel(prepared=prepared)
            raise
        except ModelProviderError as error:
            with self._session_factory() as session:
                ChatRepository(session).fail(prepared=prepared, error=error)
            yield self._event(
                prepared,
                sequence,
                "error",
                {
                    "code": error.code,
                    "message": error.safe_message,
                    "retryable": error.retryable,
                    "http_status": error.status_code,
                },
            )
        finally:
            await self._cancellations.unregister(prepared.assistant_message_id)
            prepared.lease.release()

    async def request_cancel(
        self,
        *,
        principal: Principal,
        message_id: UUID,
        request_id: str,
        trace_id: str,
    ) -> str:
        with self._session_factory() as session:
            row = ChatRepository(session).get_message(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                message_id=message_id,
            )
        if row.status == "cancelled":
            return "cancelled"
        if row.status not in {"pending", "streaming"}:
            raise ApiError(
                409,
                "MESSAGE_NOT_CANCELLABLE",
                "Conflict",
                "Only pending or streaming messages can be cancelled.",
            )
        if await self._cancellations.cancel(message_id):
            return "cancelling"
        with self._session_factory() as session:
            return ChatRepository(session).cancel_without_active_stream(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                message_id=message_id,
                request_id=request_id,
                trace_id=trace_id,
            )

    @staticmethod
    def _event(
        prepared: PreparedChat,
        sequence: int,
        event: str,
        fields: dict[str, Any],
    ) -> ChatEvent:
        return ChatEvent(
            event,
            {
                "request_id": prepared.request_id,
                "message_id": str(prepared.assistant_message_id),
                "sequence": sequence,
                "created_at": utc_now().isoformat(),
                **fields,
            },
        )


def encode_sse(event: ChatEvent) -> str:
    return (
        f"id: {event.data['sequence']}\n"
        f"event: {event.event}\n"
        f"data: {json.dumps(event.data, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


def _message_record(row: MessageRow) -> MessageRecord:
    return MessageRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        conversation_id=row.conversation_id,
        role=row.role,
        content=row.content,
        content_format=row.content_format,
        status=row.status,
        sequence_no=row.sequence_no,
        parent_message_id=row.parent_message_id,
        request_id=row.request_id,
        finish_reason=row.finish_reason,
        provider_code=row.provider_code,
        model_code=row.model_code,
        route_code=row.route_code,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cached_tokens=row.cached_tokens,
        error_code=row.error_code,
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
    )
