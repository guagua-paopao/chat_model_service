"""Add S7 UAT, release signoff and rollout evidence.

Revision ID: 20260716_0008
Revises: 20260716_0007
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260716_0008"
down_revision = "20260716_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "release_candidates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("release_version", sa.String(128), nullable=False),
        sa.Column("git_sha", sa.String(40), nullable=False),
        sa.Column("image_digest", sa.String(71), nullable=False),
        sa.Column("sbom_digest", sa.String(71), nullable=False),
        sa.Column("db_migration", sa.String(64), nullable=False),
        sa.Column("prompt_versions", sa.JSON(), nullable=False),
        sa.Column("retrieval_versions", sa.JSON(), nullable=False),
        sa.Column("model_route_versions", sa.JSON(), nullable=False),
        sa.Column("dataset_version", sa.String(128), nullable=False),
        sa.Column("eval_run_id", sa.Uuid(), sa.ForeignKey("evaluation_runs.id"), nullable=False),
        sa.Column("rollback_target", sa.String(128), nullable=False),
        sa.Column("known_issues", sa.JSON(), nullable=False),
        sa.Column("artifact_manifest", sa.JSON(), nullable=False),
        sa.Column("artifact_checksum", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("current_stage", sa.String(24), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("qualified_at", sa.DateTime(timezone=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "release_version"),
        sa.CheckConstraint(
            "status IN ('draft','qualified','approved','rolling_out','stopped',"
            "'rejected','completed','rolled_back')",
            name="release_candidates_status_ck",
        ),
        sa.CheckConstraint(
            "current_stage IN ('none','dark','percent_5','percent_25','percent_50',"
            "'percent_100','rolled_back')",
            name="release_candidates_stage_ck",
        ),
    )
    op.create_index(
        "release_candidates_tenant_created_idx", "release_candidates", ["tenant_id", "created_at"]
    )
    op.create_index(
        "release_candidates_tenant_status_idx",
        "release_candidates",
        ["tenant_id", "status", "created_at"],
    )

    op.create_table(
        "release_uat_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("release_id", sa.Uuid(), sa.ForeignKey("release_candidates.id"), nullable=False),
        sa.Column("case_id", sa.String(16), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("evidence_ref", sa.String(256), nullable=False),
        sa.Column("notes_safe", sa.String(500)),
        sa.Column("executed_by", sa.Uuid(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "release_id", "case_id"),
        sa.CheckConstraint(
            "case_id IN ('UC-01','UC-02','UC-03','UC-04','UC-05')", name="release_uat_case_ck"
        ),
        sa.CheckConstraint("result IN ('passed','failed')", name="release_uat_result_ck"),
    )
    op.create_index(
        "release_uat_release_idx", "release_uat_results", ["tenant_id", "release_id", "executed_at"]
    )

    op.create_table(
        "release_signoffs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("release_id", sa.Uuid(), sa.ForeignKey("release_candidates.id"), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("approval_id", sa.String(128), nullable=False),
        sa.Column("evidence_ref", sa.String(256), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("signed_by", sa.Uuid(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "release_id", "category"),
        sa.UniqueConstraint("tenant_id", "release_id", "signed_by"),
        sa.CheckConstraint(
            "category IN ('product','business','data','security','sre')",
            name="release_signoffs_category_ck",
        ),
        sa.CheckConstraint(
            "decision IN ('approved','rejected')", name="release_signoffs_decision_ck"
        ),
    )
    op.create_index(
        "release_signoffs_release_idx", "release_signoffs", ["tenant_id", "release_id", "signed_at"]
    )

    op.create_table(
        "release_rollout_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("release_id", sa.Uuid(), sa.ForeignKey("release_candidates.id"), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("from_stage", sa.String(24), nullable=False),
        sa.Column("to_stage", sa.String(24), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("observation", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "release_id", "sequence_no"),
        sa.CheckConstraint("decision IN ('passed','failed')", name="release_rollout_decision_ck"),
    )
    op.create_index(
        "release_rollout_release_idx",
        "release_rollout_events",
        ["tenant_id", "release_id", "sequence_no"],
    )


def downgrade() -> None:
    op.drop_index("release_rollout_release_idx", table_name="release_rollout_events")
    op.drop_table("release_rollout_events")
    op.drop_index("release_signoffs_release_idx", table_name="release_signoffs")
    op.drop_table("release_signoffs")
    op.drop_index("release_uat_release_idx", table_name="release_uat_results")
    op.drop_table("release_uat_results")
    op.drop_index("release_candidates_tenant_status_idx", table_name="release_candidates")
    op.drop_index("release_candidates_tenant_created_idx", table_name="release_candidates")
    op.drop_table("release_candidates")
