"""Add mission authoring fields consumed by DeepSearch contract compiler.

Extends the `missions` table with 11 new columns plus promotes `constraints`
to a first-class column. These fields are read by DeepSearch's
`deepsearch/worker/converter.py` when assembling the research contract from
`mission_context`. Previously they had to be smuggled through `context` JSONB,
which left the authoring contract implicit.

Additive only — every new column is nullable with no default, so existing rows
are unaffected.

Fields:
- background              TEXT        free-form background prose
- focus                   TEXT        narrow framing for the research question
- references              JSONB       array of {title: str} refs
- required_entities       JSONB       array of strings that MUST appear
- excluded_entities       JSONB       array of strings that MUST NOT appear
- expected_output_schema  JSONB       DeepSearch OutputSchema shape
- coverage_thresholds     JSONB       dict of coverage gate thresholds
- validation_thresholds   JSONB       dict of validation gate thresholds
- deliverable_format      TEXT        output rendering format hint
- max_loops               INTEGER     upper bound on DeepSearch loop budget
- min_loops               INTEGER     lower bound on DeepSearch loop budget
- constraints             JSONB       promoted from context['constraints']

Revision ID: 027_add_mission_authoring_fields
Revises: 026_add_validation_failed_status
Create Date: 2026-04-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "027_add_mission_authoring_fields"
down_revision = "026_add_validation_failed_status"
branch_labels = None
depends_on = None


NEW_COLUMNS = [
    ("background", sa.Text()),
    ("focus", sa.Text()),
    ("references", JSONB()),
    ("required_entities", JSONB()),
    ("excluded_entities", JSONB()),
    ("expected_output_schema", JSONB()),
    ("coverage_thresholds", JSONB()),
    ("validation_thresholds", JSONB()),
    ("deliverable_format", sa.Text()),
    ("max_loops", sa.Integer()),
    ("min_loops", sa.Integer()),
    ("constraints", JSONB()),
]


def upgrade() -> None:
    for name, col_type in NEW_COLUMNS:
        op.add_column("missions", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    # Refuse to drop columns if any mission has populated any of the new fields.
    # Silently dropping them would lose authored mission-contract data.
    # Column names are quoted because `references` is a Postgres reserved word.
    populated_check = " OR ".join(
        f'"{name}" IS NOT NULL' for name, _ in NEW_COLUMNS
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM missions
                WHERE {populated_check}
            ) THEN
                RAISE EXCEPTION
                  'Cannot downgrade 027: missions have populated authoring '
                  'fields (background/focus/references/required_entities/'
                  'excluded_entities/expected_output_schema/coverage_thresholds/'
                  'validation_thresholds/deliverable_format/max_loops/min_loops/'
                  'constraints). Clear them before downgrading.';
            END IF;
        END $$;
        """
    )
    for name, _ in reversed(NEW_COLUMNS):
        op.drop_column("missions", name)
