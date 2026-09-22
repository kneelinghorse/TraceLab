"""METER-0: every mission run records its usage, durably, against the user who ran it.

Data only. These tests would fail if a limit, quota or block ever crept in,
because they assert that recording never changes the outcome of a request.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api.v1.librarian as librarian_api
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.main import app
from app.models.mission import Mission
from app.models.project import Project
from app.models.usage_record import (
    ATTRIBUTION_PROJECT_OWNER,
    ATTRIBUTION_SUBMITTER,
    USAGE_KIND_DEEPSEARCH_RUN,
    USAGE_KIND_LIBRARIAN_TURN,
    UsageRecord,
)
from app.models.user import User
from app.services.librarian import LibrarianService
from app.services.librarian_model import ModelReply
from app.services.reconciler_scheduler import run_reconciliation_once
from app.services.result_materialization import MissionResultMaterializationService
from app.services.usage_recorder import (
    record_mission_terminal,
    summarize_usage,
    sweep_unrecorded_terminal_missions,
)
from tests.unit.test_usage_extraction import PRODUCTION_SHAPE


def _project(db_session, owner_id=None) -> Project:
    project = Project(name="Usage project", description="METER-0", owner_id=owner_id)
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def _mission(db_session, project, *, mission_id, status="draft", owner_id=None, execution_metadata=None) -> Mission:
    mission = Mission(
        mission_id=mission_id,
        title="Usage mission",
        objective="Prove that usage is recorded against the user who ran it.",
        success_criteria=["Recorded"],
        project_id=project.id,
        owner_id=owner_id,
        status=status,
        execution_metadata=execution_metadata or {},
        queued_at=datetime.utcnow() - timedelta(minutes=6) if status != "draft" else None,
        started_at=datetime.utcnow() - timedelta(minutes=5) if status != "draft" else None,
        completed_at=datetime.utcnow() if status in ("completed", "validation_failed") else None,
    )
    db_session.add(mission)
    db_session.commit()
    db_session.refresh(mission)
    return mission


def _run_row(db_session, mission) -> UsageRecord | None:
    return (
        db_session.query(UsageRecord)
        .filter(UsageRecord.mission_id == mission.id, UsageRecord.kind == USAGE_KIND_DEEPSEARCH_RUN)
        .first()
    )


class TestSubmitAttribution:
    def test_submit_records_a_queued_row_for_the_submitter(self, auth_headers, db_session):
        project = _project(db_session)
        mission = _mission(db_session, project, mission_id="USE-1")
        response = TestClient(app).post(f"/api/v1/missions/{mission.id}/submit", headers=auth_headers)
        assert response.status_code == 200, response.text
        row = _run_row(db_session, mission)
        assert row is not None
        assert row.status == "queued"
        assert row.attribution == ATTRIBUTION_SUBMITTER
        assert row.user_id == db_session.query(User).first().id
        assert row.project_id == project.id
        assert row.total_tokens is None

    def test_create_and_submit_records_the_submitter_too(self, auth_headers, db_session):
        project = _project(db_session)
        payload = {
            "mission_id": "USE-2",
            "title": "Create and submit",
            "objective": "Queue a mission in one call and record who did it.",
            "success_criteria": ["Recorded"],
            "project_id": str(project.id),
        }
        response = TestClient(app).post("/api/v1/missions/create-and-submit", json=payload, headers=auth_headers)
        assert response.status_code == 201, response.text
        mission = db_session.query(Mission).filter(Mission.mission_id == "USE-2").one()
        row = _run_row(db_session, mission)
        assert row is not None and row.attribution == ATTRIBUTION_SUBMITTER and row.status == "queued"


class TestTerminalRecording:
    def test_terminal_fills_the_submitter_row_from_the_worker_accounting(self, auth_headers, db_session):
        project = _project(db_session)
        mission = _mission(db_session, project, mission_id="USE-3")
        assert TestClient(app).post(f"/api/v1/missions/{mission.id}/submit", headers=auth_headers).status_code == 200
        submitter = _run_row(db_session, mission).user_id

        # The worker writes the terminal row directly; simulate exactly that.
        mission.status = "completed"
        mission.started_at = datetime.utcnow() - timedelta(minutes=5)
        mission.completed_at = datetime.utcnow()
        mission.execution_metadata = json.loads(json.dumps(PRODUCTION_SHAPE))
        db_session.commit()

        row = record_mission_terminal(db_session, mission)
        assert row is not None
        assert row.user_id == submitter and row.attribution == ATTRIBUTION_SUBMITTER
        assert row.status == "completed"
        assert (row.input_tokens, row.output_tokens, row.total_tokens) == (2182916, 36145, 2219061)
        assert row.requests == 27 and row.steps == 25 and row.tool_calls == 44
        assert row.model == "deepseek-flash" and row.provider == "deepseek"
        assert row.duration_seconds == 302.47 and row.usage_complete is True
        assert row.cost_usd is None
        assert row.completed_at == mission.completed_at
        assert db_session.query(UsageRecord).filter(UsageRecord.mission_id == mission.id).count() == 1

    def test_replay_is_idempotent_and_does_not_churn(self, db_session):
        project = _project(db_session)
        mission = _mission(db_session, project, mission_id="USE-4", status="completed", execution_metadata=PRODUCTION_SHAPE)
        first = record_mission_terminal(db_session, mission)
        stamp = first.updated_at
        again = record_mission_terminal(db_session, mission)
        assert again.id == first.id and again.updated_at == stamp
        assert db_session.query(UsageRecord).count() == 1

    def test_non_terminal_missions_are_not_recorded(self, db_session):
        project = _project(db_session)
        mission = _mission(db_session, project, mission_id="USE-5", status="in_progress")
        assert record_mission_terminal(db_session, mission) is None
        assert db_session.query(UsageRecord).count() == 0

    def test_materialization_records_usage_under_the_lock(self, db_session):
        """Both arrival routes converge in materialize(); the run row is written there."""
        project = _project(db_session)
        mission = _mission(db_session, project, mission_id="USE-6", status="completed", execution_metadata=PRODUCTION_SHAPE)
        # No result markdown or protocol: nothing to materialize, so the hook is the only write.
        result = MissionResultMaterializationService().materialize(db_session, mission)
        assert result.errors == []
        row = _run_row(db_session, mission)
        assert row is not None and row.total_tokens == 2219061 and row.attribution == ATTRIBUTION_PROJECT_OWNER


class TestSweepAndBackfill:
    def test_sweep_records_history_against_the_project_owner(self, db_session):
        owner = db_session.query(User).first()
        project = _project(db_session, owner_id=owner.id)
        done = _mission(db_session, project, mission_id="USE-7", status="completed", owner_id=owner.id, execution_metadata=PRODUCTION_SHAPE)
        failed = _mission(db_session, project, mission_id="USE-8", status="validation_failed", owner_id=owner.id, execution_metadata={"duration_seconds": 40.0})
        _mission(db_session, project, mission_id="USE-9", status="queued", owner_id=owner.id)
        assert sweep_unrecorded_terminal_missions(db_session, limit=10) == 2
        assert sweep_unrecorded_terminal_missions(db_session, limit=10) == 0
        rows = {row.mission_id: row for row in db_session.query(UsageRecord).all()}
        assert set(rows) == {done.id, failed.id}
        assert rows[done.id].attribution == ATTRIBUTION_PROJECT_OWNER and rows[done.id].user_id == owner.id
        assert rows[failed.id].status == "validation_failed" and rows[failed.id].duration_seconds == 40.0

    def test_reconciler_tick_reports_the_sweep(self, db_session, monkeypatch):
        owner = db_session.query(User).first()
        project = _project(db_session, owner_id=owner.id)
        _mission(db_session, project, mission_id="USE-10", status="completed", owner_id=owner.id, execution_metadata=PRODUCTION_SHAPE)
        counts = run_reconciliation_once()
        assert counts["usage_recorded"] == 1
        assert set(counts) >= {"scanned", "eligible", "repaired", "failed", "skipped_soft_deleted", "usage_recorded"}

    def test_cli_records_one_mission(self, db_session, capsys):
        from app.cli.record_mission_usage import main

        owner = db_session.query(User).first()
        project = _project(db_session, owner_id=owner.id)
        mission = _mission(db_session, project, mission_id="USE-11", status="completed", owner_id=owner.id, execution_metadata=PRODUCTION_SHAPE)
        assert main(["--mission-id", str(mission.id)]) == 0
        printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert printed["recorded"] == 1 and printed["total_tokens"] == 2219061 and printed["model"] == "deepseek-flash"


class TestSummary:
    def test_last_month_per_user_is_one_query(self, db_session):
        owner = db_session.query(User).first()
        project = _project(db_session, owner_id=owner.id)
        for index in range(2):
            _mission(db_session, project, mission_id=f"USE-S{index}", status="completed", owner_id=owner.id, execution_metadata=PRODUCTION_SHAPE)
        sweep_unrecorded_terminal_missions(db_session, limit=10)
        now = datetime.utcnow()
        rows = summarize_usage(db_session, since=now - timedelta(days=30), until=now + timedelta(minutes=1))
        assert rows == [
            {
                "user_id": owner.id,
                "kind": USAGE_KIND_DEEPSEARCH_RUN,
                "model": "deepseek-flash",
                "records": 2,
                "input_tokens": 2 * 2182916,
                "output_tokens": 2 * 36145,
                "total_tokens": 2 * 2219061,
                "duration_seconds": pytest.approx(2 * 302.47),
                "cost_usd": None,
            }
        ]
        assert summarize_usage(db_session, since=now - timedelta(days=30), until=now, user_id=uuid.uuid4()) == []

    def test_admin_endpoint_returns_the_summary_and_members_are_refused(self, auth_headers, db_session):
        owner = db_session.query(User).first()
        project = _project(db_session, owner_id=owner.id)
        _mission(db_session, project, mission_id="USE-A1", status="completed", owner_id=owner.id, execution_metadata=PRODUCTION_SHAPE)
        sweep_unrecorded_terminal_missions(db_session, limit=10)
        client = TestClient(app)
        response = client.get("/api/v1/admin/usage", headers=auth_headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["rows"][0]["total_tokens"] == 2219061
        assert body["rows"][0]["email"] == owner.email
        assert body["rows"][0]["kind"] == USAGE_KIND_DEEPSEARCH_RUN
        assert client.get("/api/v1/admin/usage?since=2026-02-01T00:00:00&until=2026-01-01T00:00:00", headers=auth_headers).status_code == 422

        from app.core.security import require_admin

        member = AuthenticatedUser(user_id=uuid.uuid4(), email="m@tracelab.local", display_name="m", role="member")
        app.dependency_overrides[require_authenticated_user] = lambda: member
        try:
            forbidden = client.get("/api/v1/admin/usage", headers=auth_headers)
            assert forbidden.status_code == 403, forbidden.text
        finally:
            app.dependency_overrides.pop(require_authenticated_user, None)
            app.dependency_overrides.pop(require_admin, None)


class TestLibrarianUsage:
    def test_a_turn_records_a_durable_row_for_the_caller(self, auth_headers, db_session):
        project = _project(db_session)
        model = SimpleNamespace(model_name="fake-librarian")
        model.complete = lambda messages, **kwargs: ModelReply(
            content=json.dumps({"segments": [{"kind": "prose", "text": "Hello"}]}),
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )
        app.dependency_overrides[librarian_api.get_librarian_service] = lambda: LibrarianService(model_factory=lambda: model)
        try:
            response = TestClient(app).post(
                "/api/v1/librarian/turns",
                json={"project_id": str(project.id), "messages": [{"role": "user", "content": "Hi"}]},
                headers=auth_headers,
            )
        finally:
            app.dependency_overrides.pop(librarian_api.get_librarian_service, None)
        assert response.status_code == 200, response.text
        row = db_session.query(UsageRecord).filter(UsageRecord.kind == USAGE_KIND_LIBRARIAN_TURN).one()
        assert row.user_id == db_session.query(User).first().id
        assert row.project_id == project.id and row.mission_id is None
        assert (row.input_tokens, row.output_tokens, row.total_tokens) == (10, 5, 15)
        assert row.model == "fake-librarian" and row.requests == 1
