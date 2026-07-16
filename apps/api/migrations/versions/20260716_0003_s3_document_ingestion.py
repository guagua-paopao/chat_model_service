"""Add S3 secure document ingestion, ACL, chunks, jobs and outbox.

Revision ID: 20260716_0003
Revises: 20260715_0002
Create Date: 2026-07-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260716_0003"
down_revision = "20260715_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.Column("classification", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "code"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.CheckConstraint("classification IN ('public','internal','confidential','restricted')"),
        sa.CheckConstraint("status IN ('active','archived')"),
    )
    op.create_index(
        "knowledge_bases_tenant_status_idx", "knowledge_bases", ["tenant_id", "status"]
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("classification", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("current_version_id", sa.Uuid()),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "knowledge_base_id"],
            ["knowledge_bases.tenant_id", "knowledge_bases.id"],
        ),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.CheckConstraint("classification IN ('public','internal','confidential','restricted')"),
        sa.CheckConstraint(
            "status IN ('awaiting_upload','processing','ready','failed','archived')"
        ),
    )
    op.create_index(
        "documents_kb_status_idx",
        "documents",
        ["tenant_id", "knowledge_base_id", "status"],
    )

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("declared_mime_type", sa.String(128), nullable=False),
        sa.Column("detected_mime_type", sa.String(128)),
        sa.Column("declared_size_bytes", sa.Integer(), nullable=False),
        sa.Column("actual_size_bytes", sa.Integer()),
        sa.Column("declared_sha256", sa.String(64), nullable=False),
        sa.Column("actual_sha256", sa.String(64)),
        sa.Column("quarantine_bucket", sa.String(128), nullable=False),
        sa.Column("quarantine_key", sa.String(1024), nullable=False),
        sa.Column("published_bucket", sa.String(128)),
        sa.Column("published_key", sa.String(1024)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("parser_version", sa.String(64)),
        sa.Column("chunker_version", sa.String(64)),
        sa.Column("embedding_model", sa.String(128)),
        sa.Column("embedding_version", sa.String(64)),
        sa.Column("embedding_dimensions", sa.Integer()),
        sa.Column("page_count", sa.Integer()),
        sa.Column("chunk_count", sa.Integer()),
        sa.Column("token_count", sa.Integer()),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"]
        ),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "document_id", "version_no"),
        sa.CheckConstraint("version_no >= 1"),
        sa.CheckConstraint("declared_size_bytes > 0"),
        sa.CheckConstraint(
            "status IN ('awaiting_upload','queued','processing','published','failed','archived')"
        ),
    )
    op.create_index(
        "document_versions_document_status_idx",
        "document_versions",
        ["tenant_id", "document_id", "status"],
    )

    op.create_table(
        "document_acl",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("subject_id", sa.String(128), nullable=False),
        sa.Column("permission", sa.String(16), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"]
        ),
        sa.UniqueConstraint(
            "tenant_id", "document_id", "subject_type", "subject_id", "permission"
        ),
        sa.CheckConstraint("subject_type IN ('user','group','role')"),
        sa.CheckConstraint("permission = 'read'"),
    )
    op.create_index(
        "document_acl_subject_idx",
        "document_acl",
        ["tenant_id", "subject_type", "subject_id"],
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("page_from", sa.Integer()),
        sa.Column("page_to", sa.Integer()),
        sa.Column("section_path", sa.JSON(), nullable=False),
        sa.Column("element_type", sa.String(32), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"]
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "version_id"],
            ["document_versions.tenant_id", "document_versions.id"],
        ),
        sa.UniqueConstraint("tenant_id", "version_id", "chunk_index"),
        sa.CheckConstraint("chunk_index >= 0 AND token_count > 0"),
        sa.CheckConstraint("status IN ('staged','published','archived')"),
    )
    op.create_index(
        "document_chunks_active_idx",
        "document_chunks",
        ["tenant_id", "document_id", "is_active", "chunk_index"],
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_detail_safe", sa.String(500)),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(64)),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"]
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "version_id"],
            ["document_versions.tenant_id", "document_versions.id"],
        ),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
        sa.CheckConstraint("progress BETWEEN 0 AND 100"),
        sa.CheckConstraint("attempt >= 0 AND max_attempts >= 1"),
        sa.CheckConstraint("status IN ('queued','running','completed','failed','dead_letter')"),
    )
    op.create_index(
        "ingestion_jobs_claim_idx",
        "ingestion_jobs",
        ["status", "available_at", "created_at"],
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_safe", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_version >= 1 AND attempts >= 0"),
        sa.CheckConstraint("status IN ('pending','published','failed')"),
    )
    op.create_index(
        "outbox_events_pending_idx",
        "outbox_events",
        ["status", "available_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("outbox_events_pending_idx", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ingestion_jobs_claim_idx", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_index("document_chunks_active_idx", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("document_acl_subject_idx", table_name="document_acl")
    op.drop_table("document_acl")
    op.drop_index("document_versions_document_status_idx", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index("documents_kb_status_idx", table_name="documents")
    op.drop_table("documents")
    op.drop_index("knowledge_bases_tenant_status_idx", table_name="knowledge_bases")
    op.drop_table("knowledge_bases")
