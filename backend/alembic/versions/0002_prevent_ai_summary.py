"""Add AI readiness summary to prevent runs.

Revision ID: 0002_prevent_ai_summary
Revises: 0001_initial_schema
Create Date: 2026-10-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_prevent_ai_summary"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The initial migration creates tables from current metadata, so a fresh database
    # already has this column. Add it only when an existing database lacks it.
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("prevent_runs")}
    if "ai_summary_json" not in columns:
        op.add_column("prevent_runs", sa.Column("ai_summary_json", sa.Text(), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("prevent_runs")}
    if "ai_summary_json" in columns:
        op.drop_column("prevent_runs", "ai_summary_json")
