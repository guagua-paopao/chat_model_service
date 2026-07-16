"""Add S4 pgvector hybrid retrieval, citations, feedback and RAG snapshots.

Revision ID: 20260716_0004
Revises: 20260716_0003
Create Date: 2026-07-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision = "20260716_0004"
down_revision = "20260716_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    postgresql = bind.dialect.name == "postgresql"
    if postgresql:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.add_column("document_chunks", sa.Column("embedding_vector", VECTOR()))
        op.execute(
            "UPDATE document_chunks SET embedding_vector = embedding::text::vector "
            "WHERE embedding IS NOT NULL"
        )
        op.execute(
            "CREATE INDEX document_chunks_content_fts_idx ON document_chunks "
            "USING gin (to_tsvector('simple', content))"
        )
    else:
        op.add_column("document_chunks", sa.Column("embedding_vector", sa.JSON()))
        op.execute("UPDATE document_chunks SET embedding_vector = embedding")

    op.add_column(
        "messages",
        sa.Column("response_mode", sa.String(24), nullable=False, server_default="general"),
    )
    op.add_column(
        "messages",
        sa.Column("knowledge_base_ids", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column("messages", sa.Column("rag_config_id", sa.Uuid()))
    op.add_column("messages", sa.Column("retrieval_run_id", sa.Uuid()))
    op.add_column("messages", sa.Column("prompt_version", sa.String(64)))
    op.add_column("messages", sa.Column("abstention_reason", sa.String(64)))

    op.create_table(
        "rag_configs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "code", "version"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.CheckConstraint("version >= 1"),
        sa.CheckConstraint("status IN ('draft','published','archived')"),
    )
    op.create_index(
        "rag_configs_published_idx",
        "rag_configs",
        ["tenant_id", "code", "status", "version"],
    )

    op.create_table(
        "retrieval_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("rag_config_id", sa.Uuid(), sa.ForeignKey("rag_configs.id"), nullable=False),
        sa.Column("response_mode", sa.String(24), nullable=False),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("knowledge_base_ids", sa.JSON(), nullable=False),
        sa.Column("acl_fingerprint", sa.String(64), nullable=False),
        sa.Column("knowledge_snapshot", sa.JSON(), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("reranker_model", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("abstention_reason", sa.String(64)),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.CheckConstraint("response_mode IN ('grounded_answer','search_only')"),
        sa.CheckConstraint("status IN ('completed','abstained','failed')"),
    )
    op.create_index(
        "retrieval_runs_message_idx", "retrieval_runs", ["tenant_id", "message_id"]
    )
    op.create_index(
        "retrieval_runs_created_idx", "retrieval_runs", ["tenant_id", "created_at"]
    )

    op.create_table(
        "retrieval_hits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "retrieval_run_id", sa.Uuid(), sa.ForeignKey("retrieval_runs.id"), nullable=False
        ),
        sa.Column("chunk_id", sa.Uuid(), sa.ForeignKey("document_chunks.id"), nullable=False),
        sa.Column("vector_rank", sa.Integer()),
        sa.Column("lexical_rank", sa.Integer()),
        sa.Column("fusion_rank", sa.Integer(), nullable=False),
        sa.Column("final_rank", sa.Integer(), nullable=False),
        sa.Column("vector_score", sa.Float()),
        sa.Column("lexical_score", sa.Float()),
        sa.Column("fusion_score", sa.Float(), nullable=False),
        sa.Column("rerank_score", sa.Float(), nullable=False),
        sa.Column("final_score", sa.Float(), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("source_id", sa.String(16)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "retrieval_run_id", "chunk_id"),
        sa.CheckConstraint("fusion_rank >= 1 AND final_rank >= 1"),
        sa.CheckConstraint("final_score >= 0 AND final_score <= 1"),
    )
    op.create_index(
        "retrieval_hits_run_rank_idx",
        "retrieval_hits",
        ["tenant_id", "retrieval_run_id", "final_rank"],
    )

    op.create_table(
        "citations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column(
            "retrieval_run_id", sa.Uuid(), sa.ForeignKey("retrieval_runs.id"), nullable=False
        ),
        sa.Column(
            "retrieval_hit_id", sa.Uuid(), sa.ForeignKey("retrieval_hits.id"), nullable=False
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(16), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("document_title", sa.String(300), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("page_from", sa.Integer()),
        sa.Column("page_to", sa.Integer()),
        sa.Column("section_path", sa.JSON(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "message_id", "ordinal"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.CheckConstraint("ordinal >= 1"),
    )
    op.create_index(
        "citations_message_idx", "citations", ["tenant_id", "message_id", "ordinal"]
    )

    op.create_table(
        "message_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("comment", sa.String(2000)),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "message_id", "user_id"),
        sa.CheckConstraint("rating IN (-1,1)"),
    )
    op.create_index(
        "message_feedback_message_idx", "message_feedback", ["tenant_id", "message_id"]
    )


def downgrade() -> None:
    op.drop_index("message_feedback_message_idx", table_name="message_feedback")
    op.drop_table("message_feedback")
    op.drop_index("citations_message_idx", table_name="citations")
    op.drop_table("citations")
    op.drop_index("retrieval_hits_run_rank_idx", table_name="retrieval_hits")
    op.drop_table("retrieval_hits")
    op.drop_index("retrieval_runs_created_idx", table_name="retrieval_runs")
    op.drop_index("retrieval_runs_message_idx", table_name="retrieval_runs")
    op.drop_table("retrieval_runs")
    op.drop_index("rag_configs_published_idx", table_name="rag_configs")
    op.drop_table("rag_configs")
    op.drop_column("messages", "abstention_reason")
    op.drop_column("messages", "prompt_version")
    op.drop_column("messages", "retrieval_run_id")
    op.drop_column("messages", "rag_config_id")
    op.drop_column("messages", "knowledge_base_ids")
    op.drop_column("messages", "response_mode")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS document_chunks_content_fts_idx")
    op.drop_column("document_chunks", "embedding_vector")
