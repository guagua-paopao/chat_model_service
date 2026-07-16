"""Create S1 identity, conversation and audit tables.

Revision ID: 20260715_0001
Revises: None
Create Date: 2026-07-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260715_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("default_locale", sa.String(16), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("data_classification", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active','suspended','deleting','deleted')"),
        sa.CheckConstraint(
            "data_classification IN ('public','internal','confidential','restricted')"
        ),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("auth_issuer", sa.String(512), nullable=False),
        sa.Column("auth_subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("locale", sa.String(16), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('invited','active','disabled','deleted')"),
        sa.UniqueConstraint("tenant_id", "auth_issuer", "auth_subject"),
        sa.UniqueConstraint("tenant_id", "id"),
    )
    op.create_index("users_tenant_status_idx", "users", ["tenant_id", "status"])
    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "code"),
        sa.UniqueConstraint("tenant_id", "id"),
    )
    op.create_table(
        "user_roles",
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("role_id", sa.Uuid(), primary_key=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "role_id"], ["roles.tenant_id", "roles.id"]),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("default_kb_ids", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('active','archived','deleted')"),
        sa.CheckConstraint("channel IN ('web','api','approved_connector')"),
        sa.CheckConstraint("version >= 1"),
        sa.ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"]),
        sa.UniqueConstraint("tenant_id", "id"),
    )
    op.create_index(
        "conversations_user_updated_idx",
        "conversations",
        ["tenant_id", "user_id", "updated_at", "id"],
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
        ),
        sa.UniqueConstraint("tenant_id", "conversation_id", "sequence_no"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("actor_user_id", sa.Uuid()),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128)),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(64)),
        sa.Column("details_safe", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("audit_logs_tenant_time_idx", "audit_logs", ["tenant_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("audit_logs_tenant_time_idx", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("messages")
    op.drop_index("conversations_user_updated_idx", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_index("users_tenant_status_idx", table_name="users")
    op.drop_table("users")
    op.drop_table("tenants")
