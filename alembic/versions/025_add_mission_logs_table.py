"""Add mission_logs table for DeepSearch runner log ingestion.

Sprint 39: T39.3 Mission Logs & Console Rethink

Revision ID: 025_add_mission_logs_table
Revises: 024_add_invite_codes_table
Create Date: 2026-04-11
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "025_add_mission_logs_table"
down_revision = "024_add_invite_codes_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mission_logs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "mission_id",
            sa.UUID(),
            sa.ForeignKey("missions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("level", sa.String(20), nullable=False, default="INFO"),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("source", sa.String(100), nullable=True),  # e.g. "deepsearch.runner"
        sa.Column("logged_at", sa.DateTime, nullable=False, default=datetime.utcnow),
        sa.Column("created_at", sa.DateTime, nullable=False, default=datetime.utcnow),
    )
    op.create_index("ix_mission_logs_mission_logged", "mission_logs", ["mission_id", "logged_at"])


def downgrade() -> None:
    op.drop_index("ix_mission_logs_mission_logged", table_name="mission_logs")
    op.drop_table("mission_logs")
