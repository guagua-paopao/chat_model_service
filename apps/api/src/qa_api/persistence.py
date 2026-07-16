from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    create_engine,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from qa_api.config import Settings


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TenantRow(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    default_locale: Mapped[str] = mapped_column(String(16), default="zh-CN", nullable=False)
    timezone_name: Mapped[str] = mapped_column("timezone", String(64), default="Asia/Shanghai")
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    data_classification: Mapped[str] = mapped_column(String(24), default="internal")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "auth_issuer", "auth_subject"),
        UniqueConstraint("tenant_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    auth_issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    auth_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    locale: Mapped[str] = mapped_column(String(16), default="zh-CN", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RoleRow(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code"),
        UniqueConstraint("tenant_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserRoleRow(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"]),
        ForeignKeyConstraint(["tenant_id", "role_id"], ["roles.tenant_id", "roles.id"]),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    role_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ConversationRow(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"]),
        Index("conversations_user_updated_idx", "tenant_id", "user_id", "updated_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="新对话", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    default_kb_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content_format: Mapped[str] = mapped_column(String(16), default="markdown", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_message_id: Mapped[UUID | None] = mapped_column(Uuid)
    request_id: Mapped[str | None] = mapped_column(String(128))
    finish_reason: Mapped[str | None] = mapped_column(String(32))
    provider_code: Mapped[str | None] = mapped_column(String(64))
    model_code: Mapped[str | None] = mapped_column(String(128))
    route_code: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_tokens: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_detail_safe: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
        ),
        UniqueConstraint("tenant_id", "conversation_id", "sequence_no"),
    )


class ModelInvocationRow(Base):
    __tablename__ = "model_invocations"
    __table_args__ = (
        Index("model_invocations_request_idx", "tenant_id", "request_id", "attempt_no"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    message_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("messages.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    route_code: Mapped[str] = mapped_column(String(64), nullable=False)
    route_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_code: Mapped[str] = mapped_column(String(64), nullable=False)
    model_code: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    ttft_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UsageLedgerRow(Base):
    __tablename__ = "usage_ledger"
    __table_args__ = (
        Index("usage_ledger_tenant_time_idx", "tenant_id", "created_at"),
        UniqueConstraint("tenant_id", "message_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    message_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("messages.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_code: Mapped[str] = mapped_column(String(64), nullable=False)
    model_code: Mapped[str] = mapped_column(String(128), nullable=False)
    route_code: Mapped[str] = mapped_column(String(64), nullable=False)
    route_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    price_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditLogRow(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128))
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    details_safe: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = self._create_engine(settings.database_url)
        self.session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, autoflush=False
        )

    @staticmethod
    def _create_engine(url: str) -> Engine:
        kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in url:
                kwargs["poolclass"] = StaticPool
            elif "///" in url:
                raw_path = url.split("///", 1)[1]
                if raw_path and raw_path != ":memory:":
                    Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, **kwargs)

    def sessions(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
        finally:
            session.close()

    def initialize(self) -> None:
        if self.settings.auto_create_schema:
            Base.metadata.create_all(self.engine)
        if self.settings.seed_demo_data:
            seed_demo_data(self.session_factory(), self.settings.oidc_issuer)

    def ready(self) -> bool:
        with self.session_factory() as session:
            session.execute(text("SELECT 1"))
        return True

    def dispose(self) -> None:
        self.engine.dispose()


DEMO_TENANT_ID = UUID("00000000-0000-7000-8000-000000000001")
OTHER_TENANT_ID = UUID("00000000-0000-7000-8000-000000000002")
DEMO_USER_ID = UUID("00000000-0000-7000-8000-000000000101")
DISABLED_USER_ID = UUID("00000000-0000-7000-8000-000000000102")
OTHER_USER_ID = UUID("00000000-0000-7000-8000-000000000201")
DEMO_ROLE_ID = UUID("00000000-0000-7000-8000-000000001001")
OTHER_ROLE_ID = UUID("00000000-0000-7000-8000-000000001002")


def seed_demo_data(session: Session, issuer: str) -> None:
    if session.scalar(select(TenantRow.id).where(TenantRow.id == DEMO_TENANT_ID)):
        return
    session.add_all(
        [
            TenantRow(id=DEMO_TENANT_ID, code="demo_corp", name="演示企业"),
            TenantRow(id=OTHER_TENANT_ID, code="other_corp", name="隔离测试企业"),
        ]
    )
    session.flush()
    session.add_all(
        [
            UserRow(
                id=DEMO_USER_ID,
                tenant_id=DEMO_TENANT_ID,
                auth_issuer=issuer,
                auth_subject="demo-employee",
                email="demo.employee@example.invalid",
                display_name="演示员工",
                status="active",
            ),
            UserRow(
                id=DISABLED_USER_ID,
                tenant_id=DEMO_TENANT_ID,
                auth_issuer=issuer,
                auth_subject="disabled-employee",
                email="disabled.employee@example.invalid",
                display_name="已禁用员工",
                status="disabled",
            ),
            UserRow(
                id=OTHER_USER_ID,
                tenant_id=OTHER_TENANT_ID,
                auth_issuer=issuer,
                auth_subject="other-employee",
                email="other.employee@example.invalid",
                display_name="其他租户员工",
                status="active",
            ),
            RoleRow(
                id=DEMO_ROLE_ID,
                tenant_id=DEMO_TENANT_ID,
                code="employee",
                name="员工",
                permissions=["qa:ask", "qa:conversation:read", "qa:conversation:write"],
                is_system=True,
            ),
            RoleRow(
                id=OTHER_ROLE_ID,
                tenant_id=OTHER_TENANT_ID,
                code="employee",
                name="员工",
                permissions=["qa:ask", "qa:conversation:read", "qa:conversation:write"],
                is_system=True,
            ),
        ]
    )
    session.flush()
    session.add_all(
        [
            UserRoleRow(tenant_id=DEMO_TENANT_ID, user_id=DEMO_USER_ID, role_id=DEMO_ROLE_ID),
            UserRoleRow(
                tenant_id=DEMO_TENANT_ID,
                user_id=DISABLED_USER_ID,
                role_id=DEMO_ROLE_ID,
            ),
            UserRoleRow(tenant_id=OTHER_TENANT_ID, user_id=OTHER_USER_ID, role_id=OTHER_ROLE_ID),
        ]
    )
    session.commit()
