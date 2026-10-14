"""Classify retained reports by their creation path, without deleting artifacts."""

import sqlalchemy as sa

from alembic import op

revision = "059_report_origin"
down_revision = "058_mission_log_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("reports") as batch:
        batch.add_column(sa.Column("origin", sa.String(20), nullable=False, server_default="written"))
        batch.create_check_constraint("ck_reports_origin", "origin IN ('mission', 'written', 'librarian', 'agent_brief')")
    reports = sa.table("reports", sa.column("id"), sa.column("origin"), sa.column("prompt"),
                       sa.column("report_type"), sa.column("generation_provenance", sa.JSON))
    missions = sa.table("missions", sa.column("result_report_id"))
    marker = "Auto-generated from mission "
    op.execute(reports.update().values(origin=sa.case(
        (sa.or_(reports.c.id.in_(sa.select(missions.c.result_report_id)),
                sa.func.substr(reports.c.prompt, 1, len(marker)) == marker), "mission"),
        (reports.c.report_type == "evidence-ledger", "agent_brief"),
        (reports.c.generation_provenance["origin"].as_string() == "librarian", "librarian"),
        else_="written",
    )))


def downgrade() -> None:
    with op.batch_alter_table("reports") as batch:
        batch.drop_constraint("ck_reports_origin", type_="check")
        batch.drop_column("origin")
