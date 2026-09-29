"""Guard reviewed description writes and retain their human acceptance provenance."""

import sqlalchemy as sa

from alembic import op
from app.models.types import CrossDBJSON

revision = "054_description_provenance"
down_revision = "053_report_citations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("description_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("projects", sa.Column("description_provenance", CrossDBJSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "description_provenance")
    op.drop_column("projects", "description_revision")
