from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
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
from sqlalchemy.types import TypeDecorator

from qa_api.config import Settings


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class PortableVector(TypeDecorator[list[float]]):
    """Use pgvector in PostgreSQL and JSON in fast local SQLite tests."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(VECTOR())
        return dialect.type_descriptor(JSON())


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
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    identity_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


class GroupRow(Base):
    __tablename__ = "groups"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code"),
        UniqueConstraint("tenant_id", "id"),
        Index("groups_tenant_status_idx", "tenant_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    identity_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class GroupMemberRow(Base):
    __tablename__ = "group_members"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "group_id"], ["groups.tenant_id", "groups.id"]),
        ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"]),
        Index("group_members_user_idx", "tenant_id", "user_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), primary_key=True)
    group_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), default="directory", nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeBaseRow(Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code"),
        UniqueConstraint("tenant_id", "id"),
        Index("knowledge_bases_tenant_status_idx", "tenant_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    classification: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DocumentRow(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "knowledge_base_id"],
            ["knowledge_bases.tenant_id", "knowledge_bases.id"],
        ),
        Index("documents_kb_status_idx", "tenant_id", "knowledge_base_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    knowledge_base_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    classification: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="awaiting_upload", nullable=False)
    current_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVersionRow(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "document_id", "version_no"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"]
        ),
        Index("document_versions_document_status_idx", "tenant_id", "document_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    declared_mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    detected_mime_type: Mapped[str | None] = mapped_column(String(128))
    declared_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_size_bytes: Mapped[int | None] = mapped_column(Integer)
    declared_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    actual_sha256: Mapped[str | None] = mapped_column(String(64))
    quarantine_bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    quarantine_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    published_bucket: Mapped[str | None] = mapped_column(String(128))
    published_key: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(24), default="awaiting_upload", nullable=False)
    parser_version: Mapped[str | None] = mapped_column(String(64))
    chunker_version: Mapped[str | None] = mapped_column(String(64))
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    embedding_version: Mapped[str | None] = mapped_column(String(64))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentAclRow(Base):
    __tablename__ = "document_acl"
    __table_args__ = (
        UniqueConstraint("tenant_id", "document_id", "subject_type", "subject_id", "permission"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"]
        ),
        Index("document_acl_subject_idx", "tenant_id", "subject_type", "subject_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    permission: Mapped[str] = mapped_column(String(16), default="read", nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DocumentChunkRow(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "version_id", "chunk_index"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "version_id"],
            ["document_versions.tenant_id", "document_versions.id"],
        ),
        Index(
            "document_chunks_active_idx",
            "tenant_id",
            "document_id",
            "is_active",
            "chunk_index",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page_from: Mapped[int | None] = mapped_column(Integer)
    page_to: Mapped[int | None] = mapped_column(Integer)
    section_path: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    element_type: Mapped[str] = mapped_column(String(32), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    embedding_vector: Mapped[list[float] | None] = mapped_column(PortableVector())
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="staged", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IngestionJobRow(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "idempotency_key"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "version_id"],
            ["document_versions.tenant_id", "document_versions.id"],
        ),
        Index("ingestion_jobs_claim_idx", "status", "available_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    stage: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_detail_safe: Mapped[str | None] = mapped_column(String(500))
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboxEventRow(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (Index("outbox_events_pending_idx", "status", "available_at", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_safe: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RagConfigRow(Base):
    __tablename__ = "rag_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", "version"),
        UniqueConstraint("tenant_id", "id"),
        Index("rag_configs_published_idx", "tenant_id", "code", "status", "version"),
        Index(
            "rag_configs_one_published_uq",
            "tenant_id",
            "code",
            unique=True,
            sqlite_where=text("status = 'published'"),
            postgresql_where=text("status = 'published'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    change_reason: Mapped[str] = mapped_column(String(500), default="baseline", nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(Uuid)
    rollback_of_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    approved_by: Mapped[UUID | None] = mapped_column(Uuid)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_id: Mapped[str | None] = mapped_column(String(128))
    published_by: Mapped[UUID | None] = mapped_column(Uuid)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RagConfigEvaluationRow(Base):
    __tablename__ = "rag_config_evaluations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("rag_config_evaluations_config_idx", "tenant_id", "rag_config_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    rag_config_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("rag_configs.id"), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    gate_result: Mapped[str] = mapped_column(String(16), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    failed_checks: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    response_mode: Mapped[str] = mapped_column(String(24), default="general", nullable=False)
    knowledge_base_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    rag_config_id: Mapped[UUID | None] = mapped_column(Uuid)
    retrieval_run_id: Mapped[UUID | None] = mapped_column(Uuid)
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    abstention_reason: Mapped[str | None] = mapped_column(String(64))
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


class RetrievalRunRow(Base):
    __tablename__ = "retrieval_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("retrieval_runs_message_idx", "tenant_id", "message_id"),
        Index("retrieval_runs_created_idx", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    message_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("messages.id"), nullable=False)
    rag_config_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("rag_configs.id"), nullable=False)
    response_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_base_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    acl_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    reranker_model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    abstention_reason: Mapped[str | None] = mapped_column(String(64))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RetrievalHitRow(Base):
    __tablename__ = "retrieval_hits"
    __table_args__ = (
        UniqueConstraint("tenant_id", "retrieval_run_id", "chunk_id"),
        Index("retrieval_hits_run_rank_idx", "tenant_id", "retrieval_run_id", "final_rank"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    retrieval_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("retrieval_runs.id"), nullable=False
    )
    chunk_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("document_chunks.id"), nullable=False)
    vector_rank: Mapped[int | None] = mapped_column(Integer)
    lexical_rank: Mapped[int | None] = mapped_column(Integer)
    fusion_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    final_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_score: Mapped[float | None] = mapped_column(Float)
    lexical_score: Mapped[float | None] = mapped_column(Float)
    fusion_score: Mapped[float] = mapped_column(Float, nullable=False)
    rerank_score: Mapped[float] = mapped_column(Float, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(16))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CitationRow(Base):
    __tablename__ = "citations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "message_id", "ordinal"),
        UniqueConstraint("tenant_id", "id"),
        Index("citations_message_idx", "tenant_id", "message_id", "ordinal"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    message_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("messages.id"), nullable=False)
    retrieval_run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("retrieval_runs.id"), nullable=False
    )
    retrieval_hit_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("retrieval_hits.id"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[str] = mapped_column(String(16), nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_title: Mapped[str] = mapped_column(String(300), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    page_from: Mapped[int | None] = mapped_column(Integer)
    page_to: Mapped[int | None] = mapped_column(Integer)
    section_path: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MessageFeedbackRow(Base):
    __tablename__ = "message_feedback"
    __table_args__ = (
        UniqueConstraint("tenant_id", "message_id", "user_id"),
        Index("message_feedback_message_idx", "tenant_id", "message_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    message_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("messages.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    comment: Mapped[str | None] = mapped_column(String(2000))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


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


class QuotaPolicyRow(Base):
    __tablename__ = "quota_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "scope_type", "scope_id"),
        UniqueConstraint("tenant_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    requests_per_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    concurrent_requests: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_token_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_cost_limit: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    updated_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class QuotaWindowRow(Base):
    __tablename__ = "quota_windows"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "window_kind", "window_start"),
        Index("quota_windows_expiry_idx", "window_kind", "window_start"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    window_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_tokens_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class QuotaLeaseRow(Base):
    __tablename__ = "quota_leases"
    __table_args__ = (
        Index("quota_leases_tenant_expiry_idx", "tenant_id", "expires_at"),
        Index("quota_leases_user_expiry_idx", "tenant_id", "user_id", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    input_tokens_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GovernanceAuditRow(Base):
    __tablename__ = "governance_audit_logs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sequence_no"),
        Index("governance_audit_time_idx", "tenant_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    approval_id: Mapped[str | None] = mapped_column(String(128))
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    details_safe: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SecurityIncidentRow(Base):
    __tablename__ = "security_incidents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("security_incidents_status_idx", "tenant_id", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    owner_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    resolution_safe: Mapped[str | None] = mapped_column(String(1000))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
            seed_demo_data(self.session_factory(), self.settings.oidc_issuer, self.settings)

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
CONFIG_APPROVER_USER_ID = UUID("00000000-0000-7000-8000-000000000103")
AUDITOR_USER_ID = UUID("00000000-0000-7000-8000-000000000104")
GOVERNANCE_ADMIN_USER_ID = UUID("00000000-0000-7000-8000-000000000105")
OTHER_USER_ID = UUID("00000000-0000-7000-8000-000000000201")
DEMO_ROLE_ID = UUID("00000000-0000-7000-8000-000000001001")
OTHER_ROLE_ID = UUID("00000000-0000-7000-8000-000000001002")
DEMO_KNOWLEDGE_ROLE_ID = UUID("00000000-0000-7000-8000-000000001003")
DEMO_GOVERNANCE_ROLE_ID = UUID("00000000-0000-7000-8000-000000001004")
CONFIG_APPROVER_ROLE_ID = UUID("00000000-0000-7000-8000-000000001005")
AUDITOR_ROLE_ID = UUID("00000000-0000-7000-8000-000000001006")
DEMO_GROUP_ID = UUID("00000000-0000-7000-8000-000000002001")
DEMO_QUOTA_POLICY_ID = UUID("00000000-0000-7000-8000-000000003001")


def seed_demo_data(session: Session, issuer: str, settings: Settings) -> None:
    if session.scalar(select(TenantRow.id).where(TenantRow.id == DEMO_TENANT_ID)):
        _sync_demo_issuers(session, issuer)
        _ensure_demo_knowledge_role(session)
        _ensure_s5_governance_seed(session, issuer, settings)
        session.commit()
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
                permissions=[
                    "qa:ask",
                    "qa:conversation:read",
                    "qa:conversation:write",
                    "qa:feedback",
                ],
                is_system=True,
            ),
            RoleRow(
                id=OTHER_ROLE_ID,
                tenant_id=OTHER_TENANT_ID,
                code="employee",
                name="员工",
                permissions=[
                    "qa:ask",
                    "qa:conversation:read",
                    "qa:conversation:write",
                    "qa:feedback",
                ],
                is_system=True,
            ),
            RoleRow(
                id=DEMO_KNOWLEDGE_ROLE_ID,
                tenant_id=DEMO_TENANT_ID,
                code="knowledge_admin",
                name="知识管理员",
                permissions=[
                    "qa:knowledge:read",
                    "qa:knowledge:write",
                    "qa:ingestion:read",
                    "qa:ingestion:retry",
                ],
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
                user_id=DEMO_USER_ID,
                role_id=DEMO_KNOWLEDGE_ROLE_ID,
            ),
            UserRoleRow(
                tenant_id=DEMO_TENANT_ID,
                user_id=DISABLED_USER_ID,
                role_id=DEMO_ROLE_ID,
            ),
            UserRoleRow(tenant_id=OTHER_TENANT_ID, user_id=OTHER_USER_ID, role_id=OTHER_ROLE_ID),
        ]
    )
    session.commit()
    _ensure_s5_governance_seed(session, issuer, settings)
    session.commit()


def _ensure_demo_knowledge_role(session: Session) -> None:
    for role_id in (DEMO_ROLE_ID, OTHER_ROLE_ID):
        employee_role = session.get(RoleRow, role_id)
        if employee_role is not None and "qa:feedback" not in employee_role.permissions:
            employee_role.permissions = [*employee_role.permissions, "qa:feedback"]
    role = session.get(RoleRow, DEMO_KNOWLEDGE_ROLE_ID)
    if role is None:
        session.add(
            RoleRow(
                id=DEMO_KNOWLEDGE_ROLE_ID,
                tenant_id=DEMO_TENANT_ID,
                code="knowledge_admin",
                name="知识管理员",
                permissions=[
                    "qa:knowledge:read",
                    "qa:knowledge:write",
                    "qa:ingestion:read",
                    "qa:ingestion:retry",
                ],
                is_system=True,
            )
        )
        session.flush()
    membership = session.get(
        UserRoleRow,
        {
            "tenant_id": DEMO_TENANT_ID,
            "user_id": DEMO_USER_ID,
            "role_id": DEMO_KNOWLEDGE_ROLE_ID,
        },
    )
    if membership is None:
        session.add(
            UserRoleRow(
                tenant_id=DEMO_TENANT_ID,
                user_id=DEMO_USER_ID,
                role_id=DEMO_KNOWLEDGE_ROLE_ID,
            )
        )
    session.commit()


def _sync_demo_issuers(session: Session, issuer: str) -> None:
    demo_ids = (
        DEMO_USER_ID,
        DISABLED_USER_ID,
        CONFIG_APPROVER_USER_ID,
        AUDITOR_USER_ID,
        GOVERNANCE_ADMIN_USER_ID,
        OTHER_USER_ID,
    )
    for user in session.scalars(select(UserRow).where(UserRow.id.in_(demo_ids))):
        user.auth_issuer = issuer
        user.updated_at = utc_now()
    session.flush()


def _ensure_s5_governance_seed(session: Session, issuer: str, settings: Settings) -> None:
    """Create deterministic local-only personas for governance workflow exercises."""
    users = (
        (
            GOVERNANCE_ADMIN_USER_ID,
            "governance-admin",
            "governance.admin@example.invalid",
            "Governance Administrator",
        ),
        (
            CONFIG_APPROVER_USER_ID,
            "config-approver",
            "config.approver@example.invalid",
            "Configuration Approver",
        ),
        (AUDITOR_USER_ID, "demo-auditor", "auditor@example.invalid", "Governance Auditor"),
    )
    for user_id, subject, email, display_name in users:
        if session.get(UserRow, user_id) is None:
            session.add(
                UserRow(
                    id=user_id,
                    tenant_id=DEMO_TENANT_ID,
                    auth_issuer=issuer,
                    auth_subject=subject,
                    email=email,
                    display_name=display_name,
                    status="active",
                    identity_synced_at=utc_now(),
                )
            )

    roles = (
        (
            DEMO_GOVERNANCE_ROLE_ID,
            "governance_admin",
            "Governance administrator",
            [
                "qa:admin:users:read",
                "qa:admin:users:write",
                "qa:admin:groups:read",
                "qa:admin:groups:write",
                "qa:rag-config:read",
                "qa:rag-config:write",
                "qa:rag-config:evaluate",
                "qa:rag-config:publish",
                "qa:rag-config:rollback",
                "qa:quota:read",
                "qa:quota:write",
                "qa:usage:read",
                "qa:audit:read",
                "qa:audit:verify",
                "qa:security-incident:read",
                "qa:security-incident:write",
            ],
        ),
        (
            CONFIG_APPROVER_ROLE_ID,
            "config_approver",
            "Independent configuration approver",
            ["qa:rag-config:read", "qa:rag-config:approve"],
        ),
        (
            AUDITOR_ROLE_ID,
            "auditor",
            "Read-only governance auditor",
            [
                "qa:audit:read",
                "qa:audit:verify",
                "qa:usage:read",
                "qa:security-incident:read",
            ],
        ),
    )
    for role_id, code, name, permissions in roles:
        if session.get(RoleRow, role_id) is None:
            session.add(
                RoleRow(
                    id=role_id,
                    tenant_id=DEMO_TENANT_ID,
                    code=code,
                    name=name,
                    permissions=permissions,
                    is_system=True,
                )
            )
    session.flush()

    memberships = (
        (GOVERNANCE_ADMIN_USER_ID, DEMO_GOVERNANCE_ROLE_ID),
        (CONFIG_APPROVER_USER_ID, CONFIG_APPROVER_ROLE_ID),
        (AUDITOR_USER_ID, AUDITOR_ROLE_ID),
    )
    for user_id, role_id in memberships:
        key = {"tenant_id": DEMO_TENANT_ID, "user_id": user_id, "role_id": role_id}
        if session.get(UserRoleRow, key) is None:
            session.add(UserRoleRow(**key))

    if session.get(GroupRow, DEMO_GROUP_ID) is None:
        session.add(
            GroupRow(
                id=DEMO_GROUP_ID,
                tenant_id=DEMO_TENANT_ID,
                code="all-employees",
                display_name="All employees",
                external_id="directory-group-all-employees",
                status="active",
                identity_synced_at=utc_now(),
            )
        )
        session.flush()
    for user_id in (
        DEMO_USER_ID,
        GOVERNANCE_ADMIN_USER_ID,
        CONFIG_APPROVER_USER_ID,
        AUDITOR_USER_ID,
    ):
        key = {"tenant_id": DEMO_TENANT_ID, "group_id": DEMO_GROUP_ID, "user_id": user_id}
        if session.get(GroupMemberRow, key) is None:
            session.add(GroupMemberRow(**key))

    if session.get(QuotaPolicyRow, DEMO_QUOTA_POLICY_ID) is None:
        session.add(
            QuotaPolicyRow(
                id=DEMO_QUOTA_POLICY_ID,
                tenant_id=DEMO_TENANT_ID,
                scope_type="tenant",
                scope_id=str(DEMO_TENANT_ID),
                requests_per_minute=settings.chat_requests_per_minute,
                concurrent_requests=settings.chat_tenant_concurrency,
                daily_token_limit=250_000,
                monthly_cost_limit=Decimal("100.00000000"),
                currency="USD",
                enabled=True,
                created_by=DEMO_USER_ID,
                updated_by=DEMO_USER_ID,
            )
        )
