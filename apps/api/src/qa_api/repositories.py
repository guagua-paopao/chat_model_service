from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from qa_api.cursors import CursorCodec, CursorPosition
from qa_api.domain import ApiError, ConversationRecord, Principal
from qa_api.ids import uuid7
from qa_api.persistence import (
    AuditLogRow,
    ConversationRow,
    RoleRow,
    TenantRow,
    UserRoleRow,
    UserRow,
    utc_now,
)


class IdentityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve_principal(self, *, tenant_id: UUID, issuer: str, subject: str) -> Principal:
        """Tenant scope is mandatory and cannot be sourced from request data."""
        row = self._session.execute(
            select(UserRow, TenantRow)
            .join(TenantRow, TenantRow.id == UserRow.tenant_id)
            .where(
                UserRow.tenant_id == tenant_id,
                UserRow.auth_issuer == issuer,
                UserRow.auth_subject == subject,
            )
        ).one_or_none()
        if row is None:
            raise ApiError(
                401,
                "IDENTITY_UNKNOWN",
                "Authentication required",
                "The authenticated identity is not provisioned.",
            )
        user, tenant = row
        if tenant.status != "active":
            raise ApiError(403, "TENANT_INACTIVE", "Access denied", "Tenant is not active.")
        if user.status != "active":
            raise ApiError(403, "USER_DISABLED", "Access denied", "User is not active.")

        roles = self._session.execute(
            select(RoleRow)
            .join(
                UserRoleRow,
                and_(
                    UserRoleRow.tenant_id == RoleRow.tenant_id,
                    UserRoleRow.role_id == RoleRow.id,
                ),
            )
            .where(
                UserRoleRow.tenant_id == tenant_id,
                UserRoleRow.user_id == user.id,
                or_(UserRoleRow.valid_until.is_(None), UserRoleRow.valid_until > utc_now()),
            )
        ).scalars()
        role_codes: list[str] = []
        permissions: set[str] = set()
        for role in roles:
            role_codes.append(role.code)
            permissions.update(role.permissions)
        return Principal(
            user_id=user.id,
            tenant_id=tenant.id,
            tenant_code=tenant.code,
            subject=user.auth_subject,
            display_name=user.display_name,
            locale=user.locale,
            roles=tuple(sorted(role_codes)),
            permissions=tuple(sorted(permissions)),
        )


class ConversationRepository:
    """All public operations require both tenant and user scope."""

    def __init__(self, session: Session, cursor_codec: CursorCodec) -> None:
        self._session = session
        self._cursor_codec = cursor_codec

    def create(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        title: str,
        channel: str,
        knowledge_base_ids: list[UUID],
        metadata: dict[str, object],
        request_id: str,
        trace_id: str,
    ) -> ConversationRecord:
        row = ConversationRow(
            id=uuid7(),
            tenant_id=tenant_id,
            user_id=user_id,
            title=title,
            status="active",
            channel=channel,
            default_kb_ids=[str(value) for value in knowledge_base_ids],
            metadata_json=metadata,
            version=1,
        )
        self._session.add(row)
        self._session.flush()
        self._audit(
            tenant_id=tenant_id,
            actor_user_id=user_id,
            action="conversation.create",
            resource_id=str(row.id),
            request_id=request_id,
            trace_id=trace_id,
            details={"channel": channel},
        )
        self._session.commit()
        self._session.refresh(row)
        return _conversation_record(row)

    def get(self, *, tenant_id: UUID, user_id: UUID, conversation_id: UUID) -> ConversationRecord:
        row = self._session.scalar(
            select(ConversationRow).where(
                ConversationRow.tenant_id == tenant_id,
                ConversationRow.user_id == user_id,
                ConversationRow.id == conversation_id,
                ConversationRow.deleted_at.is_(None),
            )
        )
        if row is None:
            raise ApiError(
                404,
                "CONVERSATION_NOT_FOUND",
                "Not found",
                "Conversation was not found or is not visible.",
            )
        return _conversation_record(row)

    def list(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        limit: int,
        status: str | None,
        cursor: str | None,
    ) -> tuple[list[ConversationRecord], str | None]:
        statement = select(ConversationRow).where(
            ConversationRow.tenant_id == tenant_id,
            ConversationRow.user_id == user_id,
            ConversationRow.deleted_at.is_(None),
        )
        if status is not None:
            statement = statement.where(ConversationRow.status == status)
        if cursor:
            position = self._cursor_codec.decode(
                cursor, tenant_id=tenant_id, user_id=user_id, status=status
            )
            statement = statement.where(
                or_(
                    ConversationRow.created_at < position.created_at,
                    and_(
                        ConversationRow.created_at == position.created_at,
                        ConversationRow.id < position.conversation_id,
                    ),
                )
            )
        rows = list(
            self._session.scalars(
                statement.order_by(
                    ConversationRow.created_at.desc(), ConversationRow.id.desc()
                ).limit(limit + 1)
            )
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = self._cursor_codec.encode(
                tenant_id=tenant_id,
                user_id=user_id,
                status=status,
                position=CursorPosition(last.created_at, last.id),
            )
        return [_conversation_record(row) for row in rows], next_cursor

    def update(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        conversation_id: UUID,
        expected_version: int,
        title: str | None,
        status: str | None,
        request_id: str,
        trace_id: str,
    ) -> ConversationRecord:
        values: dict[str, object] = {
            "updated_at": utc_now(),
            "version": expected_version + 1,
        }
        if title is not None:
            values["title"] = title
        if status is not None:
            values["status"] = status
        result = cast(
            CursorResult[Any],
            self._session.execute(
                update(ConversationRow)
                .where(
                    ConversationRow.tenant_id == tenant_id,
                    ConversationRow.user_id == user_id,
                    ConversationRow.id == conversation_id,
                    ConversationRow.deleted_at.is_(None),
                    ConversationRow.version == expected_version,
                )
                .values(**values)
            ),
        )
        if result.rowcount != 1:
            exists = self._session.scalar(
                select(ConversationRow.id).where(
                    ConversationRow.tenant_id == tenant_id,
                    ConversationRow.user_id == user_id,
                    ConversationRow.id == conversation_id,
                    ConversationRow.deleted_at.is_(None),
                )
            )
            self._session.rollback()
            if exists is None:
                raise ApiError(
                    404,
                    "CONVERSATION_NOT_FOUND",
                    "Not found",
                    "Conversation was not found or is not visible.",
                )
            raise ApiError(
                412,
                "ETAG_MISMATCH",
                "Precondition failed",
                "Conversation changed; reload it and retry.",
            )
        self._audit(
            tenant_id=tenant_id,
            actor_user_id=user_id,
            action="conversation.update",
            resource_id=str(conversation_id),
            request_id=request_id,
            trace_id=trace_id,
            details={"changed_fields": sorted(key for key in values if key != "updated_at")},
        )
        self._session.commit()
        return self.get(tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id)

    def delete(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        conversation_id: UUID,
        request_id: str,
        trace_id: str,
    ) -> None:
        result = cast(
            CursorResult[Any],
            self._session.execute(
                update(ConversationRow)
                .where(
                    ConversationRow.tenant_id == tenant_id,
                    ConversationRow.user_id == user_id,
                    ConversationRow.id == conversation_id,
                    ConversationRow.deleted_at.is_(None),
                )
                .values(status="deleted", deleted_at=utc_now(), updated_at=utc_now())
            ),
        )
        if result.rowcount != 1:
            self._session.rollback()
            raise ApiError(
                404,
                "CONVERSATION_NOT_FOUND",
                "Not found",
                "Conversation was not found or is not visible.",
            )
        self._audit(
            tenant_id=tenant_id,
            actor_user_id=user_id,
            action="conversation.delete",
            resource_id=str(conversation_id),
            request_id=request_id,
            trace_id=trace_id,
            details={},
        )
        self._session.commit()

    def _audit(
        self,
        *,
        tenant_id: UUID,
        actor_user_id: UUID,
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
                actor_user_id=actor_user_id,
                action=action,
                resource_type="conversation",
                resource_id=resource_id,
                result="success",
                request_id=request_id,
                trace_id=trace_id,
                details_safe=details,
            )
        )


def _conversation_record(row: ConversationRow) -> ConversationRecord:
    return ConversationRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        title=row.title,
        status=row.status,
        channel=row.channel,
        knowledge_base_ids=tuple(UUID(value) for value in row.default_kb_ids),
        metadata=dict(row.metadata_json),
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def parse_etag(value: str | None) -> int:
    if value is None:
        raise ApiError(
            428,
            "IF_MATCH_REQUIRED",
            "Precondition required",
            "If-Match is required for updates.",
        )
    normalized = value.strip()
    if not normalized.startswith('"v') or not normalized.endswith('"'):
        raise ApiError(400, "ETAG_INVALID", "Invalid request", "If-Match is invalid.")
    try:
        version = int(normalized[2:-1])
    except ValueError as exc:
        raise ApiError(400, "ETAG_INVALID", "Invalid request", "If-Match is invalid.") from exc
    if version < 1:
        raise ApiError(400, "ETAG_INVALID", "Invalid request", "If-Match is invalid.")
    return version


def etag(version: int) -> str:
    return f'"v{version}"'
