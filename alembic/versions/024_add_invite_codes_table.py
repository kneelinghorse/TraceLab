"""Add invite_codes table for user registration.

Sprint 32: Multi-User Foundation (T32.3)

Revision ID: 024_add_invite_codes_table
Revises: 023_add_users_table
Create Date: 2026-03-09
"""

import secrets
import string
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "024_add_invite_codes_table"
down_revision = "023_add_users_table"
branch_labels = None
depends_on = None

_CODE_CHARS = string.ascii_uppercase + string.digits


def _generate_code() -> str:
    return "".join(secrets.choice(_CODE_CHARS) for _ in range(8))


def upgrade() -> None:
    """Create invite_codes table and seed a bootstrap invite code."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    if "invite_codes" in existing_tables:
        return

    op.create_table(
        "invite_codes",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("code", sa.String(8), unique=True, nullable=False),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("used_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )

    op.create_index("ix_invite_codes_code", "invite_codes", ["code"], unique=True)

    # Seed a bootstrap invite code from the admin user
    admin_row = bind.execute(text("SELECT id FROM users LIMIT 1")).fetchone()
    if admin_row:
        bootstrap_code = _generate_code()
        bind.execute(
            text(
                "INSERT INTO invite_codes (id, code, created_by, created_at) "
                "VALUES (:id, :code, :created_by, :created_at)"
            ),
            {
                "id": str(uuid.uuid4()),
                "code": bootstrap_code,
                "created_by": str(admin_row[0]),
                "created_at": datetime.utcnow(),
            },
        )
        # Print the bootstrap code so the admin can share it
        print(f"\n{'=' * 60}")
        print(f"  BOOTSTRAP INVITE CODE: {bootstrap_code}")
        print(f"  Share this code to allow the first user to register.")
        print(f"{'=' * 60}\n")


def downgrade() -> None:
    """Drop invite_codes table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if "invite_codes" in inspector.get_table_names():
        op.drop_index("ix_invite_codes_code", table_name="invite_codes")
        op.drop_table("invite_codes")
