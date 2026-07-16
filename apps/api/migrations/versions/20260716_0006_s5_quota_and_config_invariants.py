"""Harden S5 active quota reservation and published config invariants.

Revision ID: 20260716_0006
Revises: 20260716_0005
Create Date: 2026-07-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260716_0006"
down_revision = "20260716_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quota_leases",
        sa.Column(
            "input_tokens_reserved", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.create_index(
        "rag_configs_one_published_uq",
        "rag_configs",
        ["tenant_id", "code"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
        sqlite_where=sa.text("status = 'published'"),
    )


def downgrade() -> None:
    op.drop_index("rag_configs_one_published_uq", table_name="rag_configs")
    op.drop_column("quota_leases", "input_tokens_reserved")
