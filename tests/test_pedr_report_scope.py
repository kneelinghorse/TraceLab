"""PEDR-1C authorization and source-persistence boundaries for reports."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from app.api.v1 import reports as reports_api
from app.api.v1 import synthesize as synthesize_api
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import ROLE_MEMBER, AuthenticatedUser
from app.main import app
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.document import Document
from app.models.project import Project
from app.models.report import Report, ReportSource
from app.models.user import User
from app.schemas.report import ReportCreate
from app.schemas.synthesis import SynthesizeRequest
from app.services.report_service import ReportService
from app.services.synthesis import SynthesisService


def _principal() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=uuid4(),
        email="report-member@example.com",
        display_name="report-member",
        role=ROLE_MEMBER,
    )


def _project(db, *, name: str) -> Project:
    project = Project(name=name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _chunk(db, *, project_id: UUID, content: str) -> DocumentChunk:
    document = Document(project_id=project_id, name=f"{content} document")
    db.add(document)
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content=content,
        content_tsv=text("''"),
    )
    db.add(chunk)
    db.commit()
    db.refresh(chunk)
    return chunk


def _report_model(*, title: str = "Scoped report") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        title=title,
        content="Scoped content",
        tokens_used=0,
        status="draft",
        created_at=datetime.utcnow(),
    )


class _RecordingReportService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create_report(self, **kwargs):
        self.calls.append(kwargs)
        return _report_model(title=kwargs["title"]), []


class _RecordingSynthesis:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.calls: list[dict] = []

    def synthesize(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class _RecordingCache:
    def __init__(self) -> None:
        self.get_calls: list[dict] = []
        self.set_calls: list[dict] = []

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return None

    def set(self, **kwargs):
        self.set_calls.append(kwargs)
        return "cache-id"


def test_report_create_rejects_collection_and_chunks_as_http_422(auth_headers):
    """An ambiguous source request is rejected by schema validation, not service logic."""
    response = TestClient(app).post(
        "/api/v1/reports",
        json={
            "title": "Ambiguous",
            "collection_id": str(uuid4()),
            "chunk_ids": [str(uuid4())],
        },
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert "either collection_id or chunk_ids" in response.text.lower()


def test_report_create_schema_treats_present_empty_chunks_as_ambiguous():
    """Supplying both fields stays ambiguous even when chunk_ids is an empty list."""
    with pytest.raises(ValidationError, match="either collection_id or chunk_ids"):
        ReportCreate(
            title="Ambiguous",
            collection_id=uuid4(),
            chunk_ids=[],
        )


def test_unrestricted_report_route_preserves_exact_legacy_service_call(monkeypatch):
    """None scope omits the new keyword and avoids scoped resource lookups."""
    principal = _principal()
    service = _RecordingReportService()
    events: list[str] = []

    def _scope(_user, _db):
        events.append("scope")
        return None

    def _factory():
        events.append("factory")
        return service

    monkeypatch.setattr(reports_api, "accessible_project_ids", _scope)
    monkeypatch.setattr(reports_api, "default_workspace_id", lambda _db: uuid4())

    response = reports_api.create_report(
        ReportCreate(title="Legacy", chunk_ids=[uuid4()]),
        current_user=principal,
        db=object(),
        service_factory=_factory,
    )

    assert response.title == "Legacy"
    assert events == ["scope", "factory"]
    assert len(service.calls) == 1
    assert "accessible_project_ids" not in service.calls[0]


def test_scoped_report_route_authorizes_targets_before_service_factory(monkeypatch):
    """Collection and report-project checks both precede service construction."""
    principal = _principal()
    collection = Collection(name="Authorized collection")
    project = Project(name="Authorized target")
    collection.id = uuid4()
    project.id = uuid4()
    project_scope = [project.id]
    service = _RecordingReportService()
    events: list[tuple[str, object]] = []

    class _LookupDB:
        def get(self, model, identifier):
            if model is Collection and identifier == collection.id:
                return collection
            if model is Project and identifier == project.id:
                return project
            raise AssertionError((model, identifier))

    def _authorize(_user, action, resource, _db):
        events.append((action, resource))

    def _factory():
        assert events == [("read", collection), ("create", project)]
        return service

    monkeypatch.setattr(
        reports_api,
        "accessible_project_ids",
        lambda _user, _db: project_scope,
    )
    monkeypatch.setattr(reports_api, "authorize_or_403", _authorize)
    monkeypatch.setattr(reports_api, "default_workspace_id", lambda _db: uuid4())

    response = reports_api.create_report(
        ReportCreate(
            title="Scoped",
            collection_id=collection.id,
            project_id=project.id,
        ),
        current_user=principal,
        db=_LookupDB(),
        service_factory=_factory,
    )

    assert response.title == "Scoped"
    assert service.calls[0]["accessible_project_ids"] == project_scope


def test_foreign_report_target_is_403_before_report_service(
    monkeypatch, db_session
):
    """A scoped caller cannot associate a new report with another tenant's project."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    project = _project(db_session, name="Foreign target")

    with pytest.raises(HTTPException) as exc_info:
        reports_api.create_report(
            ReportCreate(
                title="Denied",
                chunk_ids=[uuid4()],
                project_id=project.id,
            ),
            current_user=_principal(),
            db=db_session,
            service_factory=lambda: pytest.fail(
                "foreign project constructed the report service"
            ),
        )

    assert exc_info.value.status_code == 403


def test_foreign_report_collection_is_403_before_report_service(
    monkeypatch, db_session
):
    """An existing collection outside the caller's tenant is denied before IO."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    collection = Collection(name="Foreign report collection", owner_id=uuid4())
    db_session.add(collection)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        reports_api.create_report(
            ReportCreate(title="Denied", collection_id=collection.id),
            current_user=_principal(),
            db=db_session,
            service_factory=lambda: pytest.fail(
                "foreign collection constructed the report service"
            ),
        )

    assert exc_info.value.status_code == 403


def test_missing_report_collection_is_404_before_report_service(
    monkeypatch, db_session
):
    """A valid but absent collection UUID is distinguished from a foreign row."""
    monkeypatch.setattr(settings, "rbac_enabled", True)

    with pytest.raises(HTTPException) as exc_info:
        reports_api.create_report(
            ReportCreate(title="Missing collection", collection_id=uuid4()),
            current_user=_principal(),
            db=db_session,
            service_factory=lambda: pytest.fail(
                "missing collection constructed the report service"
            ),
        )

    assert exc_info.value.status_code == 404


def test_missing_report_target_project_is_404_before_report_service(
    monkeypatch, db_session
):
    """A valid but absent report target cannot reach synthesis construction."""
    monkeypatch.setattr(settings, "rbac_enabled", True)

    with pytest.raises(HTTPException) as exc_info:
        reports_api.create_report(
            ReportCreate(
                title="Missing target",
                chunk_ids=[uuid4()],
                project_id=uuid4(),
            ),
            current_user=_principal(),
            db=db_session,
            service_factory=lambda: pytest.fail(
                "missing target project constructed the report service"
            ),
        )

    assert exc_info.value.status_code == 404


def test_soft_deleted_report_target_is_404_before_report_service(
    monkeypatch, db_session
):
    """Deleted projects are not valid report targets even for their former owner."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    caller = _principal()
    project = Project(
        name="Deleted report target",
        owner_id=caller.user_id,
        deleted_at=datetime.utcnow(),
    )
    db_session.add(project)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        reports_api.create_report(
            ReportCreate(
                title="Deleted target",
                chunk_ids=[uuid4()],
                project_id=project.id,
            ),
            current_user=caller,
            db=db_session,
            service_factory=lambda: pytest.fail(
                "deleted target constructed the report service"
            ),
        )

    assert exc_info.value.status_code == 404


def test_foreign_synthesis_report_target_is_403_before_provider(
    monkeypatch, db_session
):
    """save_as_report applies the same target-project gate before synthesis."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    project = _project(db_session, name="Foreign synthesis target")

    with pytest.raises(HTTPException) as exc_info:
        synthesize_api.synthesize(
            SynthesizeRequest(
                chunk_ids=[uuid4()],
                save_as_report=True,
                report_title="Denied",
                project_id=project.id,
            ),
            current_user=_principal(),
            db=db_session,
            service_factory=lambda: pytest.fail(
                "foreign report target constructed the synthesis service"
            ),
        )

    assert exc_info.value.status_code == 403


def test_soft_deleted_synthesis_report_target_is_404_before_provider(
    monkeypatch, db_session
):
    """One-call report creation rejects deleted project targets before providers."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    caller = _principal()
    project = Project(
        name="Deleted synthesis target",
        owner_id=caller.user_id,
        deleted_at=datetime.utcnow(),
    )
    db_session.add(project)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        synthesize_api.synthesize(
            SynthesizeRequest(
                chunk_ids=[uuid4()],
                save_as_report=True,
                report_title="Deleted target",
                project_id=project.id,
            ),
            current_user=caller,
            db=db_session,
            service_factory=lambda: pytest.fail(
                "deleted target constructed the synthesis service"
            ),
        )

    assert exc_info.value.status_code == 404


def test_scoped_direct_synthesis_report_persists_only_effective_chunk_ids(
    monkeypatch, db_session
):
    """The one-call synthesis path cannot snapshot a filtered foreign chunk."""
    caller = _principal()
    db_session.add(
        User(
            id=caller.user_id,
            email=caller.email,
            display_name=caller.display_name,
            password_hash="not-a-real-hash",  # noqa: S106
            role=caller.role,
        )
    )
    db_session.commit()
    allowed_project_id = uuid4()
    allowed_chunk_id = uuid4()
    foreign_chunk_id = uuid4()
    synthesis = _RecordingSynthesis(
        {
            "content": "Only authorized content",
            "citations": [],
            "tokens_used": 3,
            "chunk_count": 1,
            "effective_chunk_ids": [str(allowed_chunk_id)],
        }
    )
    monkeypatch.setattr(
        synthesize_api,
        "accessible_project_ids",
        lambda _user, _db: [allowed_project_id],
    )

    response = synthesize_api.synthesize(
        SynthesizeRequest(
            chunk_ids=[allowed_chunk_id, foreign_chunk_id],
            save_as_report=True,
            report_title="Scoped direct synthesis",
        ),
        current_user=caller,
        db=db_session,
        service_factory=lambda: synthesis,
    )

    assert response.report_id is not None
    assert synthesis.calls[0]["accessible_project_ids"] == [allowed_project_id]
    db_session.expire_all()
    report = db_session.get(Report, response.report_id)
    assert report is not None
    assert report.chunk_count == 1
    assert report.owner_id == caller.user_id
    assert {(source.source_type, source.source_id) for source in report.sources} == {
        ("chunk", allowed_chunk_id)
    }


def test_scoped_collection_synthesis_empty_result_persists_collection_only(
    monkeypatch, db_session
):
    """A filtered mixed collection remains attributable without leaking child IDs."""
    caller = _principal()
    collection = Collection(
        name="Scoped empty collection",
        owner_id=caller.user_id,
    )
    db_session.add_all(
        [
            User(
                id=caller.user_id,
                email=caller.email,
                display_name=caller.display_name,
                password_hash="not-a-real-hash",  # noqa: S106
                role=caller.role,
            ),
            collection,
        ]
    )
    db_session.commit()
    allowed_project_id = uuid4()
    synthesis = _RecordingSynthesis(
        {
            "content": "No content available from the selected sources.",
            "citations": [],
            "tokens_used": 0,
            "chunk_count": 0,
            "effective_chunk_ids": [],
        }
    )
    monkeypatch.setattr(settings, "rbac_enabled", True)
    monkeypatch.setattr(
        synthesize_api,
        "accessible_project_ids",
        lambda _user, _db: [allowed_project_id],
    )

    response = synthesize_api.synthesize(
        SynthesizeRequest(
            collection_id=collection.id,
            save_as_report=True,
            report_title="Scoped collection synthesis",
        ),
        current_user=caller,
        db=db_session,
        service_factory=lambda: synthesis,
    )

    assert response.report_id is not None
    assert synthesis.calls[0]["accessible_project_ids"] == [allowed_project_id]
    db_session.expire_all()
    report = db_session.get(Report, response.report_id)
    assert report is not None
    assert report.chunk_count == 0
    assert {(source.source_type, source.source_id) for source in report.sources} == {
        ("collection", collection.id)
    }


def test_scoped_collection_report_snapshots_only_cache_hit_effective_chunks(
    db_session,
):
    """Persistence never re-expands a mixed collection after scoped synthesis."""
    allowed_project = _project(db_session, name="Allowed")
    foreign_project = _project(db_session, name="Foreign")
    allowed_chunk = _chunk(
        db_session,
        project_id=allowed_project.id,
        content="allowed source",
    )
    foreign_chunk = _chunk(
        db_session,
        project_id=foreign_project.id,
        content="foreign source",
    )
    collection = Collection(name="Mixed")
    db_session.add(collection)
    db_session.flush()
    db_session.add_all(
        [
            CollectionItem(collection_id=collection.id, chunk_id=allowed_chunk.id),
            CollectionItem(collection_id=collection.id, chunk_id=foreign_chunk.id),
        ]
    )
    db_session.commit()

    synthesis = _RecordingSynthesis(
        {
            "content": "Cached allowed synthesis",
            "citations": [],
            "tokens_used": 2,
            "chunk_count": 1,
            "cache_hit": True,
            "effective_chunk_ids": [str(allowed_chunk.id)],
        }
    )
    service = ReportService(
        session_factory=SessionLocal,
        synthesis_service=synthesis,
    )

    report, _citations = service.create_report(
        title="Mixed collection report",
        collection_id=collection.id,
        accessible_project_ids=[allowed_project.id],
    )

    sources = (
        db_session.query(ReportSource)
        .filter(ReportSource.report_id == report.id)
        .all()
    )
    assert len(sources) == 2
    assert {(source.source_type, str(source.source_id)) for source in sources} == {
        ("collection", str(collection.id)),
        ("chunk", str(allowed_chunk.id)),
    }
    assert synthesis.calls[0]["accessible_project_ids"] == [allowed_project.id]


def test_scoped_direct_report_snapshots_only_effective_chunks(db_session):
    """Foreign requested chunk IDs cannot survive as scoped report sources."""
    allowed_project = _project(db_session, name="Allowed direct")
    allowed_chunk_id = uuid4()
    foreign_chunk_id = uuid4()
    synthesis = _RecordingSynthesis(
        {
            "content": "Allowed direct synthesis",
            "citations": [],
            "tokens_used": 1,
            "chunk_count": 1,
            "effective_chunk_ids": [allowed_chunk_id],
        }
    )
    service = ReportService(
        session_factory=SessionLocal,
        synthesis_service=synthesis,
    )

    report, _citations = service.create_report(
        title="Direct report",
        chunk_ids=[allowed_chunk_id, foreign_chunk_id],
        accessible_project_ids=[allowed_project.id],
    )

    sources = (
        db_session.query(ReportSource)
        .filter(ReportSource.report_id == report.id)
        .all()
    )
    assert [str(source.source_id) for source in sources] == [str(allowed_chunk_id)]


def test_empty_scope_creates_empty_report_without_synthesis_provider(db_session):
    """Batch report creation may persist an empty 201 artifact without LLM/cache use."""
    synthesis = _RecordingSynthesis({})
    service = ReportService(
        session_factory=SessionLocal,
        synthesis_service=synthesis,
    )

    report, citations = service.create_report(
        title="Empty report",
        chunk_ids=[uuid4()],
        accessible_project_ids=[],
    )

    assert report.chunk_count == 0
    assert report.content.startswith("No content available")
    assert citations == []
    assert synthesis.calls == []
    assert (
        db_session.query(ReportSource)
        .filter(ReportSource.report_id == report.id)
        .count()
        == 0
    )


def test_all_foreign_report_skips_provider_and_cache(db_session):
    """A nonempty scope with no effective inputs also creates an empty report safely."""
    allowed_project = _project(db_session, name="Allowed empty")
    foreign_project = _project(db_session, name="Foreign input")
    foreign_chunk = _chunk(
        db_session,
        project_id=foreign_project.id,
        content="foreign secret",
    )
    client = MagicMock()
    cache = _RecordingCache()
    synthesis = SynthesisService(
        session_factory=SessionLocal,
        client=client,
        cache_service=cache,
        cost_monitor=MagicMock(),
    )
    service = ReportService(
        session_factory=SessionLocal,
        synthesis_service=synthesis,
    )

    report, citations = service.create_report(
        title="All foreign",
        chunk_ids=[foreign_chunk.id],
        accessible_project_ids=[allowed_project.id],
    )

    assert report.chunk_count == 0
    assert citations == []
    client.chat.completions.create.assert_not_called()
    assert cache.get_calls == []
    assert cache.set_calls == []
    assert (
        db_session.query(ReportSource)
        .filter(ReportSource.report_id == report.id)
        .count()
        == 0
    )


def test_none_scope_keeps_legacy_collection_snapshot_and_call_shape(db_session):
    """Unrestricted collection reports still snapshot every collection item."""
    project = _project(db_session, name="Legacy")
    first = _chunk(db_session, project_id=project.id, content="first")
    second = _chunk(db_session, project_id=project.id, content="second")
    collection = Collection(name="Legacy collection")
    db_session.add(collection)
    db_session.flush()
    db_session.add_all(
        [
            CollectionItem(collection_id=collection.id, chunk_id=first.id),
            CollectionItem(collection_id=collection.id, chunk_id=second.id),
        ]
    )
    db_session.commit()
    synthesis = _RecordingSynthesis(
        {
            "content": "Legacy synthesis",
            "citations": [],
            "tokens_used": 1,
            "chunk_count": 2,
        }
    )
    service = ReportService(
        session_factory=SessionLocal,
        synthesis_service=synthesis,
    )

    report, _citations = service.create_report(
        title="Legacy report",
        collection_id=collection.id,
    )

    assert "accessible_project_ids" not in synthesis.calls[0]
    sources = (
        db_session.query(ReportSource)
        .filter(
            ReportSource.report_id == report.id,
            ReportSource.source_type == "chunk",
        )
        .all()
    )
    assert {str(source.source_id) for source in sources} == {
        str(first.id),
        str(second.id),
    }
