"""Postgres enforces what SQLite ignores: claiming a mission email must lock only the mission row.

Mission.result_report is eager-loaded through a LEFT OUTER JOIN, and PostgreSQL refuses
FOR UPDATE on the nullable side of an outer join. Production hit this on 2026-09-15.
"""

from uuid import uuid4

from app.core.config import settings
from app.models.mission import Mission
from app.models.user import User
from app.services import notifications


def test_a_completed_mission_can_be_claimed_once_on_postgres(db_session, monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")
    monkeypatch.setattr(settings, "resend_from_address", "TraceLab <notifications@tracelab.aquex.ai>")
    monkeypatch.setattr(settings, "notification_emails_enabled", True)
    owner = User(email=f"{uuid4().hex}@owners.tracelab.aquex.ai", display_name="Owner", password_hash="placeholder-not-a-real-hash", role="member")
    db_session.add(owner)
    db_session.flush()
    mission = Mission(
        mission_id=f"NOTIFY-PG-{uuid4().hex[:6]}", title="Research the market", objective="Find the evidence",
        success_criteria=["Cite sources"], status="completed", owner_id=owner.id,
    )
    db_session.add(mission)
    db_session.commit()

    claimed = notifications.claim_terminal_notification(db_session, mission.id)

    assert claimed is not None
    _, email, claim = claimed
    assert email.to == owner.email
    assert claim["status"] == "completed"
    # The claim is committed, so a duplicate webhook finds this status already taken.
    assert notifications.claim_terminal_notification(db_session, mission.id) is None
