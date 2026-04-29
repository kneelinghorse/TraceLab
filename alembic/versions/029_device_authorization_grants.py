"""Create device_authorization_grants table for RFC 8628 device-code flow.

T42.4 (sprint-42) — backs the new MCP installer login UX. The MCP client
hits POST /api/v1/auth/device/code, the user types the short user_code into
the web /device page, MCP polls /device/token until the row flips to
approved + an api_keys row is minted on the user's behalf.

Revision ID: 029_device_authorization_grants
Revises: 028_drop_research_depth
Create Date: 2026-04-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "029_device_authorization_grants"
down_revision = "028_drop_research_depth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_authorization_grants",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("device_code", sa.String(64), nullable=False, unique=True),
        sa.Column("user_code", sa.String(16), nullable=False, unique=True),
        sa.Column("client_label", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "api_key_id",
            sa.UUID(),
            sa.ForeignKey("api_keys.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_polled_at", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'denied', 'expired')",
            name="valid_device_grant_status",
        ),
    )
    op.create_index(
        "ix_device_grants_user_code",
        "device_authorization_grants",
        ["user_code"],
    )
    op.create_index(
        "ix_device_grants_device_code",
        "device_authorization_grants",
        ["device_code"],
    )
    op.create_index(
        "ix_device_grants_status",
        "device_authorization_grants",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_device_grants_status", table_name="device_authorization_grants")
    op.drop_index("ix_device_grants_device_code", table_name="device_authorization_grants")
    op.drop_index("ix_device_grants_user_code", table_name="device_authorization_grants")
    op.drop_table("device_authorization_grants")
