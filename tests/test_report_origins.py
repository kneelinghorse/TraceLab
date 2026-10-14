"""Written documents remain discoverable without losing mission artifacts or access checks."""

from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.collection import Collection
from app.models.evidence_ledger import LedgerNote
from app.models.report import Report, ReportSource
from tests.test_home_api import actor, mission
from tests.test_reports_api import _create_test_chunk, _create_test_document, _create_test_project


def test_origins_filter_before_count_and_paging_but_default_keeps_every_artifact(db_session, auth_headers):
    rows = [Report(title=origin, content="Retained text", origin=origin)
            for origin in ("mission", "written", "librarian", "agent_brief")]
    db_session.add_all(rows)
    db_session.commit()
    with TestClient(app) as client:
        assert client.get("/api/v1/reports", headers=auth_headers).json()["total"] == 4
        response = client.get("/api/v1/reports?origin=written&origin=librarian&page_size=1", headers=auth_headers)
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 2
        assert len(response.json()["items"]) == 1
        assert response.json()["items"][0]["origin"] in {"written", "librarian"}
        assert client.get("/api/v1/reports?origin=guessed", headers=auth_headers).status_code == 422


def test_report_labels_and_named_sources_follow_current_access(db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user, headers = actor(db_session)
    other, _ = actor(db_session)
    project = _create_test_project(db_session)
    project.owner_id = user.id
    doc = _create_test_document(db_session, project.id)
    chunk = _create_test_chunk(db_session, doc.id)
    collection = Collection(name="Reviewed findings", owner_id=user.id)
    report = Report(title="Readable report", content="Retained prose", owner_id=user.id,
                    project_id=project.id, origin="written", chunk_count=1)
    db_session.add_all([collection, report])
    db_session.flush()
    db_session.add_all([ReportSource(report_id=report.id, source_type=kind, source_id=identity)
                        for kind, identity in (("collection", collection.id), ("chunk", chunk.id))])
    db_session.commit()
    with TestClient(app) as client:
        detail = client.get(f"/api/v1/reports/{report.id}", headers=headers).json()
        assert detail["origin_label"] == "Written from collection Reviewed findings"
        assert detail["origin_href"] == f"/collections/{collection.id}"
        assert detail["project_name"] == project.name
        assert {s["name"] for s in detail["sources"]} == {collection.name, doc.name}
        assert all(s["href"] for s in detail["sources"])
        collection.owner_id = other.id
        project.owner_id = other.id
        db_session.commit()
        detail = client.get(f"/api/v1/reports/{report.id}", headers=headers).json()
        assert detail["content"] == "Retained prose"
        assert detail["origin_label"] == "Written from 1 excerpt"
        assert detail["origin_href"] is None and detail["project_name"] is None
        assert all(s["name"] == "Source unavailable" and s["href"] is None and s["source_id"] is None
                   for s in detail["sources"])
        assert collection.name not in str(detail) and doc.name not in str(detail)


def test_mission_origin_links_only_to_readable_mission_and_orphans_remain(db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user, headers = actor(db_session)
    other, _ = actor(db_session)
    report = Report(title="Copy", content="Saved result", origin="mission", owner_id=user.id)
    db_session.add(report)
    db_session.flush()
    run = mission(db_session, owner_id=user.id, result_report_id=report.id)
    db_session.commit()
    with TestClient(app) as client:
        row = client.get("/api/v1/reports?origin=mission", headers=headers).json()["items"][0]
        assert row["origin_label"] == f"Results of mission {run.title}"
        assert row["origin_href"] == f"/missions/{run.id}?tab=results"
        run.owner_id = other.id
        db_session.commit()
        row = client.get("/api/v1/reports?origin=mission", headers=headers).json()["items"][0]
        assert row["origin_label"] == "Mission results" and row["origin_href"] is None
        assert db_session.query(Report).count() == 1


def test_home_excludes_duplicate_results_while_project_counts_written_documents(db_session, auth_headers):
    project = _create_test_project(db_session)
    rows = [Report(title=origin, content="Saved", origin=origin, project_id=project.id)
            for origin in ("written", "librarian", "agent_brief", "mission")]
    db_session.add_all(rows)
    db_session.flush()
    mission(db_session, "in_progress", result_report_id=rows[-1].id, started_at=datetime.utcnow())
    db_session.commit()
    with TestClient(app) as client:
        home = client.get("/api/v1/home", headers=auth_headers).json()
        assert home["recent_reports"]["total"] == 3
        assert {r["title"] for r in home["recent_reports"]["items"]} == {"written", "librarian", "agent_brief"}
        assert str(rows[-1].id) not in {r["id"] for r in home["activity"]["items"]}
        # Filtering Home documents must not erase a running mission's existing result link.
        assert home["active_runs"]["items"][0]["report_id"] == str(rows[-1].id)
        stats = client.get(f"/api/v1/projects/{project.id}/stats", headers=auth_headers).json()
        assert stats["report_count"] == 2


def test_unknown_source_has_no_uuid_stub(db_session, auth_headers):
    report = Report(title="Old source", content="Retained", origin="written")
    db_session.add(report)
    db_session.flush()
    db_session.add(ReportSource(report_id=report.id, source_type="collection", source_id=uuid4()))
    db_session.commit()
    with TestClient(app) as client:
        source = client.get(f"/api/v1/reports/{report.id}", headers=auth_headers).json()["sources"][0]
        assert source["name"] == "Source unavailable" and source["href"] is None and source["source_id"] is None


def test_note_only_brief_links_to_its_readable_session_without_leaking_revoked_notes(db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user, headers = actor(db_session)
    other, _ = actor(db_session)
    project = _create_test_project(db_session)
    project.owner_id = user.id
    report = Report(title="Working brief", content="Saved prose", origin="agent_brief", owner_id=user.id)
    note = LedgerNote(project_id=project.id, owner_id=user.id, session_key="review-session",
                      note_key="next", content="Working state")
    db_session.add_all([report, note])
    db_session.flush()
    db_session.add(ReportSource(report_id=report.id, source_type="ledger_note", source_id=note.id))
    db_session.commit()
    with TestClient(app) as client:
        detail = client.get(f"/api/v1/reports/{report.id}", headers=headers).json()
        expected = f"/evidence?project_id={project.id}&session_key=review-session"
        assert detail["origin_href"] == detail["sources"][0]["href"] == expected
        assert detail["sources"][0]["name"] == "Working note"
        project.owner_id = other.id
        note.owner_id = other.id
        db_session.commit()
        detail = client.get(f"/api/v1/reports/{report.id}", headers=headers).json()
        assert detail["origin_href"] is None
        assert detail["sources"][0]["source_id"] is None
        assert detail["sources"][0]["name"] == "Source unavailable"
        assert "review-session" not in str(detail)
