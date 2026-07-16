"""Add S6 versioned quality evaluation runs.

Revision ID: 20260716_0007
Revises: 20260716_0006
Create Date: 2026-07-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260716_0007"
down_revision = "20260716_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("dataset_version_id", sa.String(128), nullable=False),
        sa.Column("dataset_checksum", sa.String(64), nullable=False),
        sa.Column("candidate_config_ids", sa.JSON(), nullable=False),
        sa.Column("candidate_config_snapshots", sa.JSON(), nullable=False),
        sa.Column("baseline_run_id", sa.Uuid()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("thresholds", sa.JSON(), nullable=False),
        sa.Column("deltas", sa.JSON(), nullable=False),
        sa.Column("gate_result", sa.String(16), nullable=False),
        sa.Column("failed_cases", sa.JSON(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 8), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("code_revision", sa.String(128), nullable=False),
        sa.Column("evaluator_version", sa.String(64), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.CheckConstraint("status IN ('completed','failed')", name="evaluation_runs_status_ck"),
        sa.CheckConstraint("gate_result IN ('passed','failed')", name="evaluation_runs_gate_ck"),
        sa.CheckConstraint("amount >= 0", name="evaluation_runs_amount_ck"),
    )
    op.create_index(
        "evaluation_runs_tenant_created_idx",
        "evaluation_runs",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "evaluation_runs_tenant_gate_idx",
        "evaluation_runs",
        ["tenant_id", "gate_result", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("evaluation_runs_tenant_gate_idx", table_name="evaluation_runs")
    op.drop_index("evaluation_runs_tenant_created_idx", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
