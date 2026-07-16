"""Add S5 enterprise governance, immutable config gates and shared quotas.

Revision ID: 20260716_0005
Revises: 20260716_0004
Create Date: 2026-07-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260716_0005"
down_revision = "20260716_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column("users", sa.Column("identity_synced_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("disabled_at", sa.DateTime(timezone=True)))

    op.create_table(
        "groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("external_id", sa.String(255)),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("identity_synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "code"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.CheckConstraint("status IN ('active','disabled')", name="groups_status_ck"),
    )
    op.create_index("groups_tenant_status_idx", "groups", ["tenant_id", "status"])
    op.create_table(
        "group_members",
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("group_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="directory"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "group_id"], ["groups.tenant_id", "groups.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"]),
    )
    op.create_index("group_members_user_idx", "group_members", ["tenant_id", "user_id"])

    op.add_column(
        "rag_configs",
        sa.Column("evaluation_status", sa.String(24), nullable=False, server_default="pending"),
    )
    op.add_column(
        "rag_configs",
        sa.Column(
            "change_reason", sa.String(500), nullable=False, server_default="legacy baseline"
        ),
    )
    op.add_column("rag_configs", sa.Column("supersedes_id", sa.Uuid()))
    op.add_column("rag_configs", sa.Column("rollback_of_id", sa.Uuid()))
    op.add_column("rag_configs", sa.Column("approved_by", sa.Uuid()))
    op.add_column("rag_configs", sa.Column("approved_at", sa.DateTime(timezone=True)))
    op.add_column("rag_configs", sa.Column("approval_id", sa.String(128)))
    op.add_column("rag_configs", sa.Column("published_by", sa.Uuid()))
    op.execute("UPDATE rag_configs SET evaluation_status = 'passed' WHERE status = 'published'")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("rag_configs_status_check", "rag_configs", type_="check")
        op.create_check_constraint(
            "rag_configs_status_s5_ck",
            "rag_configs",
            "status IN ('draft','evaluated','approved','published','archived')",
        )
    op.create_table(
        "rag_config_evaluations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "rag_config_id", sa.Uuid(), sa.ForeignKey("rag_configs.id"), nullable=False
        ),
        sa.Column("dataset_version", sa.String(128), nullable=False),
        sa.Column("dataset_checksum", sa.String(64), nullable=False),
        sa.Column("evaluator_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("gate_result", sa.String(16), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("thresholds", sa.JSON(), nullable=False),
        sa.Column("failed_checks", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.CheckConstraint("status = 'completed'", name="rag_config_eval_status_ck"),
        sa.CheckConstraint(
            "gate_result IN ('passed','failed')", name="rag_config_eval_result_ck"
        ),
    )
    op.create_index(
        "rag_config_evaluations_config_idx",
        "rag_config_evaluations",
        ["tenant_id", "rag_config_id", "created_at"],
    )

    op.create_table(
        "quota_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(128), nullable=False),
        sa.Column("requests_per_minute", sa.Integer(), nullable=False),
        sa.Column("concurrent_requests", sa.Integer(), nullable=False),
        sa.Column("daily_token_limit", sa.Integer(), nullable=False),
        sa.Column("monthly_cost_limit", sa.Numeric(18, 8), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "scope_type", "scope_id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.CheckConstraint("scope_type IN ('tenant','user')", name="quota_scope_ck"),
    )
    op.create_table(
        "quota_windows",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("window_kind", sa.String(16), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("input_tokens_reserved", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", "window_kind", "window_start"),
    )
    op.create_index("quota_windows_expiry_idx", "quota_windows", ["window_kind", "window_start"])
    op.create_table(
        "quota_leases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "quota_leases_tenant_expiry_idx", "quota_leases", ["tenant_id", "expires_at"]
    )
    op.create_index(
        "quota_leases_user_expiry_idx",
        "quota_leases",
        ["tenant_id", "user_id", "expires_at"],
    )

    op.create_table(
        "governance_audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("approval_id", sa.String(128)),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(64)),
        sa.Column("details_safe", sa.JSON(), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "sequence_no"),
    )
    op.create_index(
        "governance_audit_time_idx", "governance_audit_logs", ["tenant_id", "occurred_at"]
    )

    op.create_table(
        "security_incidents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("resolution_safe", sa.String(1000)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.CheckConstraint("severity IN ('P0','P1','P2','P3')", name="incident_severity_ck"),
        sa.CheckConstraint(
            "status IN ('open','triaged','contained','resolved','closed')",
            name="incident_status_ck",
        ),
    )
    op.create_index(
        "security_incidents_status_idx",
        "security_incidents",
        ["tenant_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("security_incidents_status_idx", table_name="security_incidents")
    op.drop_table("security_incidents")
    op.drop_index("governance_audit_time_idx", table_name="governance_audit_logs")
    op.drop_table("governance_audit_logs")
    op.drop_index("quota_leases_user_expiry_idx", table_name="quota_leases")
    op.drop_index("quota_leases_tenant_expiry_idx", table_name="quota_leases")
    op.drop_table("quota_leases")
    op.drop_index("quota_windows_expiry_idx", table_name="quota_windows")
    op.drop_table("quota_windows")
    op.drop_table("quota_policies")
    op.drop_index("rag_config_evaluations_config_idx", table_name="rag_config_evaluations")
    op.drop_table("rag_config_evaluations")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("rag_configs_status_s5_ck", "rag_configs", type_="check")
        op.create_check_constraint(
            "rag_configs_status_check",
            "rag_configs",
            "status IN ('draft','published','archived')",
        )
    for column in (
        "published_by",
        "approval_id",
        "approved_at",
        "approved_by",
        "rollback_of_id",
        "supersedes_id",
        "change_reason",
        "evaluation_status",
    ):
        op.drop_column("rag_configs", column)
    op.drop_index("group_members_user_idx", table_name="group_members")
    op.drop_table("group_members")
    op.drop_index("groups_tenant_status_idx", table_name="groups")
    op.drop_table("groups")
    op.drop_column("users", "disabled_at")
    op.drop_column("users", "identity_synced_at")
    op.drop_column("users", "version")
