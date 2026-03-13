"""Mission Protocol validation constraint and schema metadata.

Revision ID: 004_mission_protocol_validation
Revises: 003_onboarding
Create Date: 2025-11-07 22:15:00.000000
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

from app.services.mission_protocol_validation import (
    build_mission_data_check_constraint,
    mission_protocol_schema,
)

# revision identifiers, used by Alembic.
revision = "004_mission_protocol_validation"
down_revision = "003_onboarding"
branch_labels = None
depends_on = None

CHECK_NAME = "missions_mission_data_check"


def upgrade() -> None:
    constraint_sql = build_mission_data_check_constraint()
    op.create_check_constraint(
        CHECK_NAME,
        "missions",
        constraint_sql,
    )

    conn = op.get_bind()
    upsert_stmt = text(
        """
        INSERT INTO metadata (key, value)
        VALUES (:key, :value)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """
    )
    schemas = [
        {
            "key": "mission_protocol_schema_draft",
            "value": json.dumps(mission_protocol_schema("draft")),
        },
        {
            "key": "mission_protocol_schema_complete",
            "value": json.dumps(mission_protocol_schema("complete")),
        },
    ]
    for payload in schemas:
        conn.execute(upsert_stmt, payload)


def downgrade() -> None:
    op.drop_constraint(CHECK_NAME, "missions", type_="check")
    conn = op.get_bind()
    conn.execute(
        text("DELETE FROM metadata WHERE key IN (:draft_key, :complete_key)"),
        {
            "draft_key": "mission_protocol_schema_draft",
            "complete_key": "mission_protocol_schema_complete",
        },
    )
