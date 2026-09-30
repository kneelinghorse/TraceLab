"""Add nullable attempt/event identity while retaining all legacy log history."""

import sqlalchemy as sa

from alembic import op
from app.models.types import GUID

revision = '058_mission_log_attempts'
down_revision = '057_password_recovery_audit'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('mission_logs') as batch:
        batch.add_column(sa.Column('attempt_count', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('event_id', GUID(), nullable=True))
        batch.add_column(sa.Column('sequence', sa.Integer(), nullable=True))
        batch.create_unique_constraint('uq_mission_log_event', ['mission_id', 'attempt_count', 'event_id'])
        batch.create_unique_constraint('uq_mission_log_sequence', ['mission_id', 'attempt_count', 'sequence'])
        batch.create_check_constraint('ck_mission_log_identity', '(attempt_count IS NULL AND event_id IS NULL AND sequence IS NULL) OR (attempt_count IS NOT NULL AND attempt_count > 0 AND event_id IS NOT NULL AND sequence IS NOT NULL AND sequence > 0)')


def downgrade() -> None:
    with op.batch_alter_table('mission_logs') as batch:
        batch.drop_constraint('ck_mission_log_identity', type_='check')
        batch.drop_constraint('uq_mission_log_sequence', type_='unique')
        batch.drop_constraint('uq_mission_log_event', type_='unique')
        batch.drop_column('sequence')
        batch.drop_column('event_id')
        batch.drop_column('attempt_count')
