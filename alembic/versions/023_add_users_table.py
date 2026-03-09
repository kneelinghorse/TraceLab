"""Add users table for multi-user authentication.

Creates the users table with seed admin backfill from AUTH_USERNAME/AUTH_PASSWORD_HASH
env vars. Migrates api_keys.user_id from String to UUID FK referencing users.id.

Sprint 32: Multi-User Foundation (T32.1)

Revision ID: 023_add_users_table
Revises: 022_graph_edges
Create Date: 2026-03-09
"""

import os
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "023_add_users_table"
down_revision = "022_graph_edges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create users table, seed admin, migrate api_keys.user_id to UUID FK."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    if "users" in existing_tables:
        return

    # 1. Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="admin"),
        sa.Column("invite_code_used", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
    )

    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # 2. Seed admin user from env vars
    admin_id = uuid.uuid4()
    auth_username = os.environ.get("AUTH_USERNAME", "tracelab-admin")
    auth_password_hash = os.environ.get("AUTH_PASSWORD_HASH", "")

    # If no hash provided, try to hash the plain password
    if not auth_password_hash:
        auth_password = os.environ.get("AUTH_PASSWORD", "changeme")
        import bcrypt
        auth_password_hash = bcrypt.hashpw(
            auth_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    # Use username as email if it doesn't look like an email
    admin_email = auth_username if "@" in auth_username else f"{auth_username}@tracelab.local"

    bind.execute(
        text(
            "INSERT INTO users (id, email, display_name, password_hash, role, created_at, updated_at) "
            "VALUES (:id, :email, :display_name, :password_hash, :role, :created_at, :updated_at)"
        ),
        {
            "id": str(admin_id),
            "email": admin_email,
            "display_name": auth_username,
            "password_hash": auth_password_hash,
            "role": "admin",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        },
    )

    # 3. Migrate api_keys.user_id from String to UUID FK
    # Step 3a: Add new UUID column
    op.add_column("api_keys", sa.Column("user_id_new", sa.UUID(), nullable=True))

    # Step 3b: Backfill existing rows to point at seed admin
    bind.execute(
        text("UPDATE api_keys SET user_id_new = :admin_id"),
        {"admin_id": str(admin_id)},
    )

    # Step 3c: Drop old column and rename
    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_column("api_keys", "user_id")
    op.alter_column("api_keys", "user_id_new", new_column_name="user_id", nullable=False)

    # Step 3d: Add FK and index
    op.create_foreign_key(
        "fk_api_keys_user_id", "api_keys", "users", ["user_id"], ["id"]
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])


def downgrade() -> None:
    """Drop users table and revert api_keys.user_id to String."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    # Revert api_keys.user_id to String
    if "api_keys" in existing_tables:
        op.drop_constraint("fk_api_keys_user_id", "api_keys", type_="foreignkey")
        op.drop_index("ix_api_keys_user_id", table_name="api_keys")
        op.add_column("api_keys", sa.Column("user_id_old", sa.String(), nullable=True, server_default="default"))
        bind = op.get_bind()
        bind.execute(text("UPDATE api_keys SET user_id_old = 'default'"))
        op.drop_column("api_keys", "user_id")
        op.alter_column("api_keys", "user_id_old", new_column_name="user_id", nullable=False)
        op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])

    if "users" in existing_tables:
        op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")
