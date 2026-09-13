"""Admin totals must stay independent of the six recent rows on PostgreSQL."""

from uuid import uuid4

import pytest
from sqlalchemy import func

from app.adapters.repositories.sqlalchemy_admin_stats_repo import SQLAlchemyAdminStatsRepository
from app.models.mission import Mission

pytestmark = pytest.mark.integration


def test_whole_database_counts_on_postgres(db_session):
    for _ in range(143):
        db_session.add(
            Mission(
                mission_id=uuid4().hex,
                title="Admin counts",
                objective="Observe all work",
                success_criteria=["Full count"],
                status="completed",
            )
        )
    db_session.commit()
    snapshot = SQLAlchemyAdminStatsRepository().snapshot(db_session)
    direct = dict(db_session.query(Mission.status, func.count()).group_by(Mission.status))
    assert snapshot.missions.total == sum(direct.values()) >= 143
    assert snapshot.missions.by_status["completed"] >= 143
    assert {k: v for k, v in snapshot.missions.by_status.items() if v} == direct
    assert len(snapshot.recent_missions) == 6
