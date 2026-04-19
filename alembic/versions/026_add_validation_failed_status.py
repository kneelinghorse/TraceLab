"""Add validation_failed to valid_mission_status CHECK constraint.

Supports DeepSearch Sprint 30 fail-closed outcome model where a mission can
synthesize a report but fail coverage or structural gates. This outcome is
distinct from `blocked` (which means execution could not proceed) and must be
persisted so reviewers see validation failures as reviewable artifacts rather
than infra errors.

Additive only — no existing rows are affected.

Revision ID: 026_add_validation_failed_status
Revises: 025_add_mission_logs_table
Create Date: 2026-04-19
"""
from __future__ import annotations

from alembic import op

revision = "026_add_validation_failed_status"
down_revision = "025_add_mission_logs_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE missions DROP CONSTRAINT IF EXISTS valid_mission_status")
    op.execute(
        """
        ALTER TABLE missions
        ADD CONSTRAINT valid_mission_status
        CHECK (status IN (
            'draft', 'queued', 'in_progress',
            'completed', 'blocked', 'cancelled', 'validation_failed'
        ))
        """
    )


def downgrade() -> None:
    # Refuse to downgrade while rows with the new status exist — dropping them
    # silently would lose DeepSearch fail-closed outcomes.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM missions WHERE status = 'validation_failed') THEN
                RAISE EXCEPTION
                  'Cannot downgrade: missions with status=validation_failed exist. '
                  'Reclassify or delete them before downgrading.';
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE missions DROP CONSTRAINT IF EXISTS valid_mission_status")
    op.execute(
        """
        ALTER TABLE missions
        ADD CONSTRAINT valid_mission_status
        CHECK (status IN (
            'draft', 'queued', 'in_progress',
            'completed', 'blocked', 'cancelled'
        ))
        """
    )
