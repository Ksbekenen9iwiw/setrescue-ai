"""Create the SetRescue MVP schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-09
"""
from __future__ import annotations

from alembic import op

from app.database import Base
from app import models  # noqa: F401

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The initial migration is generated directly from the pinned declarative metadata.
    # Subsequent schema changes should use explicit Alembic operations/autogeneration.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
