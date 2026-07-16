"""Add S2 model invocation, streaming message and usage ledger fields.

Revision ID: 20260715_0002
Revises: 20260715_0001
Create Date: 2026-07-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260715_0002"
down_revision = "20260715_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.add_column(
            sa.Column("content_format", sa.String(16), nullable=False, server_default="markdown")
        )
        batch.add_column(sa.Column("parent_message_id", sa.Uuid()))
        batch.add_column(sa.Column("request_id", sa.String(128)))
        batch.add_column(sa.Column("finish_reason", sa.String(32)))
        batch.add_column(sa.Column("provider_code", sa.String(64)))
        batch.add_column(sa.Column("model_code", sa.String(128)))
        batch.add_column(sa.Column("route_code", sa.String(64)))
        batch.add_column(sa.Column("input_tokens", sa.Integer()))
        batch.add_column(sa.Column("output_tokens", sa.Integer()))
        batch.add_column(sa.Column("cached_tokens", sa.Integer()))
        batch.add_column(sa.Column("error_code", sa.String(64)))
        batch.add_column(sa.Column("error_detail_safe", sa.String(500)))
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True)))

    op.create_table(
        "model_invocations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(64)),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("route_code", sa.String(64), nullable=False),
        sa.Column("route_version", sa.String(64), nullable=False),
        sa.Column("provider_code", sa.String(64), nullable=False),
        sa.Column("model_code", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("ttft_ms", sa.Integer()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("attempt_no >= 1"),
        sa.CheckConstraint("status IN ('started','completed','failed','cancelled')"),
    )
    op.create_index(
        "model_invocations_request_idx",
        "model_invocations",
        ["tenant_id", "request_id", "attempt_no"],
    )

    op.create_table(
        "usage_ledger",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("provider_code", sa.String(64), nullable=False),
        sa.Column("model_code", sa.String(128), nullable=False),
        sa.Column("route_code", sa.String(64), nullable=False),
        sa.Column("route_version", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated", sa.Boolean(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 8), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("price_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "message_id"),
        sa.CheckConstraint("input_tokens >= 0 AND output_tokens >= 0 AND cached_tokens >= 0"),
        sa.CheckConstraint("amount >= 0"),
    )
    op.create_index(
        "usage_ledger_tenant_time_idx", "usage_ledger", ["tenant_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("usage_ledger_tenant_time_idx", table_name="usage_ledger")
    op.drop_table("usage_ledger")
    op.drop_index("model_invocations_request_idx", table_name="model_invocations")
    op.drop_table("model_invocations")
    with op.batch_alter_table("messages") as batch:
        for column in [
            "completed_at",
            "updated_at",
            "error_detail_safe",
            "error_code",
            "cached_tokens",
            "output_tokens",
            "input_tokens",
            "route_code",
            "model_code",
            "provider_code",
            "finish_reason",
            "request_id",
            "parent_message_id",
            "content_format",
        ]:
            batch.drop_column(column)
