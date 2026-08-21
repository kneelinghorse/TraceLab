"""PEDR related/preflight project-scope regression tests.

These tests encode the security boundary: an inaccessible graph node is not a
bridge to accessible data, and an empty preflight scope performs no search.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.api.v1 import pedr_related as pedr_related_api
from app.api.v1.pedr_preflight import preflight_query
from app.api.v1.pedr_related import get_related_entities
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import ROLE_SERVICE, AuthenticatedUser
from app.models import (
    Document,
    DocumentChunk,
    Insight,
    Mission,
    Project,
    Report,
)
from app.schemas.pedr_preflight import PreflightQuery
from app.services.pedr.preflight import PreflightService
from app.services.pedr.relational import (
    EntityType,
    GraphExpansionResult,
    RelatedEntity,
    RelationalService,
    RelationType,
)


class _RecordingSearch:
    def __init__(self, results: list[dict[str, Any]] | None = None) -> None:
        self.results = results or []
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        return [dict(result) for result in self.results]


def _user(*, role: str = "member") -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=uuid4(),
        email="pedr-scope@example.test",
        display_name="pedr-scope",
        role=role,
    )


def _mission(
    project: Project,
    suffix: str,
    *,
    result_document_ids: list[str] | None = None,
    result_report_id: UUID | None = None,
) -> Mission:
    return Mission(
        project_id=project.id,
        mission_id=f"PEDR-{suffix}",
        title=f"Mission {suffix}",
        objective=f"Research objective {suffix}",
        success_criteria=["Scope is enforced"],
        result_document_ids=result_document_ids or [],
        result_report_id=result_report_id,
    )


def _related_call(
    urn: str,
    *,
    db: Any,
    user: AuthenticatedUser,
) -> Any:
    return asyncio.run(
        get_related_entities(
            urn=urn,
            max_depth=2,
            limit=50,
            include_types=None,
            exclude_types=None,
            relation_types=None,
            db=db,
            current_user=user,
        )
    )


def _empty_expansion(urn: str, **kwargs: Any) -> GraphExpansionResult:
    entity_type, entity_id = RelationalService().parse_urn(urn)
    return GraphExpansionResult(
        source_urn=urn,
        source_entity_type=entity_type,
        source_entity_id=entity_id,
        related_entities=[],
        total_found=0,
        expansion_depth=kwargs.get("max_depth", 2),
    )


def test_related_route_loads_and_authorizes_all_six_root_types(db_session):
    """Every supported URN resolves an ORM root; chunks inherit their document."""
    project = Project(name="Allowed project")
    db_session.add(project)
    db_session.flush()

    document = Document(project_id=project.id, name="Root document")
    mission = _mission(project, "ROOT")
    insight = Insight(
        project_id=project.id,
        title="Root insight",
        content="Insight content",
    )
    report = Report(
        project_id=project.id,
        title="Root report",
        content="Report content",
    )
    db_session.add_all([document, mission, insight, report])
    db_session.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="Root chunk",
    )
    db_session.add(chunk)
    db_session.commit()

    roots = [
        ("project", project.id, project),
        ("document", document.id, document),
        ("chunk", chunk.id, document),
        ("mission", mission.id, mission),
        ("insight", insight.id, insight),
        ("report", report.id, report),
    ]
    fake_service = MagicMock(spec=RelationalService)
    parser = RelationalService(session=db_session)
    fake_service.parse_urn.side_effect = parser.parse_urn
    fake_service.get_related.side_effect = _empty_expansion
    caller = _user()

    with (
        patch(
            "app.api.v1.pedr_related.get_relational_service",
            return_value=fake_service,
        ),
        patch("app.api.v1.pedr_related.authorize_or_403") as authorize,
        patch(
            "app.api.v1.pedr_related.accessible_project_ids",
            return_value=[project.id],
        ),
    ):
        for entity_type, entity_id, _ in roots:
            response = _related_call(
                f"urn:research:{entity_type}:{entity_id}",
                db=db_session,
                user=caller,
            )
            assert response.source_entity_type == entity_type

    assert [call.args[2] for call in authorize.call_args_list] == [
        root for _, _, root in roots
    ]
    assert all(
        call.kwargs["session"] is db_session
        and call.kwargs["allowed_project_ids"] == [project.id]
        for call in fake_service.get_related.call_args_list
    )


def test_related_route_returns_404_before_authorization_for_absent_root(db_session):
    fake_service = MagicMock(spec=RelationalService)
    fake_service.parse_urn.side_effect = RelationalService().parse_urn

    with (
        patch(
            "app.api.v1.pedr_related.get_relational_service",
            return_value=fake_service,
        ),
        patch("app.api.v1.pedr_related.authorize_or_403") as authorize,
        pytest.raises(HTTPException) as exc_info,
    ):
        _related_call(
            f"urn:research:mission:{uuid4()}",
            db=db_session,
            user=_user(),
        )

    assert exc_info.value.status_code == 404
    authorize.assert_not_called()
    fake_service.get_related.assert_not_called()


def test_related_route_does_not_disclose_internal_exception_text(db_session):
    project = Project(name="Exception boundary")
    db_session.add(project)
    db_session.commit()
    failure = RuntimeError("private database token=do-not-disclose")
    fake_service = MagicMock(spec=RelationalService)
    fake_service.parse_urn.side_effect = RelationalService().parse_urn
    fake_service.get_related.side_effect = failure

    with (
        patch(
            "app.api.v1.pedr_related.get_relational_service",
            return_value=fake_service,
        ),
        patch("app.api.v1.pedr_related.authorize_or_403"),
        patch(
            "app.api.v1.pedr_related.accessible_project_ids",
            return_value=[project.id],
        ),
        patch("app.api.v1.pedr_related.logger.exception") as log_exception,
        pytest.raises(HTTPException) as exc_info,
    ):
        _related_call(
            f"urn:research:project:{project.id}",
            db=db_session,
            user=_user(),
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == pedr_related_api.INTERNAL_ERROR_DETAIL
    assert "private database token" not in exc_info.value.detail
    log_exception.assert_called_once_with("Graph expansion failed: %s", failure)


def test_related_scope_prunes_cross_project_mission_result_edges(db_session):
    """A mission cannot expose result documents or reports from another project."""
    allowed_project = Project(name="Allowed")
    denied_project = Project(name="Denied")
    db_session.add_all([allowed_project, denied_project])
    db_session.flush()

    denied_document = Document(project_id=denied_project.id, name="Denied document")
    denied_report = Report(
        project_id=denied_project.id,
        title="Denied report",
        content="Private report",
    )
    db_session.add_all([denied_document, denied_report])
    db_session.flush()
    mission = _mission(
        allowed_project,
        "CROSS",
        result_document_ids=[str(denied_document.id)],
        result_report_id=denied_report.id,
    )
    db_session.add(mission)
    db_session.commit()

    service = RelationalService(session=db_session)
    urn = f"urn:research:mission:{mission.id}"
    scoped = service.get_related(
        urn,
        max_depth=1,
        allowed_project_ids=[allowed_project.id],
    )
    unscoped = service.get_related(urn, max_depth=1)

    scoped_ids = {entity.entity_id for entity in scoped.related_entities}
    unscoped_ids = {entity.entity_id for entity in unscoped.related_entities}
    assert str(allowed_project.id) in scoped_ids
    assert str(denied_document.id) not in scoped_ids
    assert str(denied_report.id) not in scoped_ids
    assert {str(denied_document.id), str(denied_report.id)} <= unscoped_ids


def test_related_scope_prunes_cross_project_report_parent(db_session):
    allowed_project = Project(name="Allowed")
    denied_project = Project(name="Denied")
    db_session.add_all([allowed_project, denied_project])
    db_session.flush()
    denied_parent = Report(
        project_id=denied_project.id,
        title="Denied parent",
        content="Private parent report",
    )
    db_session.add(denied_parent)
    db_session.flush()
    child = Report(
        project_id=allowed_project.id,
        parent_id=denied_parent.id,
        title="Allowed child",
        content="Visible child report",
    )
    db_session.add(child)
    db_session.commit()

    service = RelationalService(session=db_session)
    urn = f"urn:research:report:{child.id}"
    scoped = service.get_related(
        urn,
        max_depth=1,
        allowed_project_ids=[allowed_project.id],
    )
    unscoped = service.get_related(urn, max_depth=1)

    assert str(denied_parent.id) not in {
        entity.entity_id for entity in scoped.related_entities
    }
    assert str(denied_parent.id) in {
        entity.entity_id for entity in unscoped.related_entities
    }


def test_related_scope_does_not_traverse_through_denied_result_document(db_session):
    """A denied result-document edge cannot become a bridge back into scope."""
    allowed_project = Project(name="Allowed")
    denied_project = Project(name="Denied")
    db_session.add_all([allowed_project, denied_project])
    db_session.flush()
    denied_document = Document(project_id=denied_project.id, name="Denied bridge")
    allowed_report = Report(
        project_id=allowed_project.id,
        title="Would leak through bridge",
        content="Allowed but unreachable",
    )
    mission = _mission(allowed_project, "BRIDGE")
    db_session.add_all([denied_document, allowed_report, mission])
    db_session.commit()

    service = RelationalService(session=db_session)
    visited_types: list[EntityType] = []

    def neighbors(
        _session: Any,
        entity_type: EntityType,
        _entity_id: str,
        **_kwargs: Any,
    ) -> list[RelatedEntity]:
        visited_types.append(entity_type)
        if entity_type == EntityType.MISSION:
            return [
                RelatedEntity(
                    entity_type=EntityType.DOCUMENT,
                    entity_id=str(denied_document.id),
                    relation_type=RelationType.REFERENCES,
                    relation_direction="outbound",
                    distance=1,
                )
            ]
        if entity_type == EntityType.DOCUMENT:
            return [
                RelatedEntity(
                    entity_type=EntityType.REPORT,
                    entity_id=str(allowed_report.id),
                    relation_type=RelationType.REFERENCES,
                    relation_direction="outbound",
                    distance=1,
                )
            ]
        return []

    with patch.object(service, "_get_neighbors", side_effect=neighbors):
        result = service.get_related(
            f"urn:research:mission:{mission.id}",
            max_depth=2,
            allowed_project_ids=[allowed_project.id],
        )

    assert result.related_entities == []
    assert visited_types == [EntityType.MISSION]


def test_related_empty_scope_skips_neighbor_queries(db_session):
    service = RelationalService(session=db_session)
    with patch.object(service, "_get_neighbors") as get_neighbors:
        result = service.get_related(
            f"urn:research:project:{uuid4()}",
            allowed_project_ids=[],
        )

    assert result.total_found == 0
    get_neighbors.assert_not_called()


def test_related_denied_root_skips_graph_traversal(db_session):
    """Scope applies to the root itself, not only to discovered neighbors."""
    allowed_project = Project(name="Allowed root scope")
    denied_project = Project(name="Denied root scope")
    db_session.add_all([allowed_project, denied_project])
    db_session.flush()
    denied_mission = _mission(denied_project, "DENIED-ROOT")
    db_session.add(denied_mission)
    db_session.commit()

    service = RelationalService(session=db_session)
    with patch.object(service, "_get_neighbors") as get_neighbors:
        result = service.get_related(
            f"urn:research:mission:{denied_mission.id}",
            allowed_project_ids=[allowed_project.id],
        )

    assert result.related_entities == []
    assert result.total_found == 0
    get_neighbors.assert_not_called()


def test_enrichment_threads_scope_without_storing_request_state(db_session):
    service = RelationalService(session=db_session)
    project_id = uuid4()
    result = {"chunk_id": str(uuid4()), "content": "Scoped result"}
    expansion = GraphExpansionResult(
        source_urn="urn:research:chunk:test",
        source_entity_type=EntityType.CHUNK,
        source_entity_id="test",
        related_entities=[],
        total_found=0,
        expansion_depth=1,
    )

    with patch.object(service, "get_related", return_value=expansion) as get_related:
        service.enrich_search_results(
            [result],
            allowed_project_ids=[project_id],
        )
        service.enrich_search_results([result])

    scoped_call, unscoped_call = get_related.call_args_list
    assert scoped_call.kwargs["allowed_project_ids"] == [project_id]
    assert "allowed_project_ids" not in unscoped_call.kwargs
    assert not hasattr(service, "allowed_project_ids")


def test_preflight_nonempty_scope_reaches_search_and_metadata_loader():
    project_id = uuid4()
    document_id = str(uuid4())
    search = _RecordingSearch(
        [{"document_id": document_id, "score": 0.91, "project_id": str(project_id)}]
    )
    service = PreflightService(
        search_service=search,
        session_factory=MagicMock(),
        telemetry_enabled=False,
    )
    metadata_calls: list[tuple[list[str], list[UUID] | None]] = []

    def load_metadata(
        document_ids: list[str],
        *,
        allowed_project_ids: list[UUID] | None = None,
    ) -> dict[str, dict[str, Any]]:
        metadata_calls.append((document_ids, allowed_project_ids))
        return {
            document_id: {
                "mission_uuid": str(uuid4()),
                "mission_data": {
                    "mission_id": "PEDR-SCOPED",
                    "title": "Scoped mission",
                    "research_statement": {"objective": "Scoped objective"},
                },
                "status": "complete",
                "quality_gates_passed": 5,
                "quality_gates_total": 5,
                "quality_score": 1.0,
            }
        }

    with patch.object(service, "_load_mission_metadata", side_effect=load_metadata):
        recommendation = service.query(
            PreflightQuery(query="scoped research"),
            allowed_project_ids=[project_id],
        )

    assert search.calls[0]["allowed_project_ids"] == [project_id]
    assert metadata_calls == [([document_id], [project_id])]
    assert recommendation.match_count == 1


def test_preflight_loader_uses_canonical_mission_fields(db_session):
    """Preflight reads the current Mission schema and canonical identity fields."""
    project = Project(name="Canonical preflight project")
    db_session.add(project)
    db_session.flush()
    mission = Mission(
        project_id=project.id,
        mission_id="PEDR-CANONICAL",
        title="Canonical mission title",
        objective="Canonical mission objective",
        success_criteria=["Canonical fields are loaded"],
        tags=["canonical"],
        context={
            "mission_id": "PEDR-STALE",
            "title": "Stale context title",
            "research_statement": {"objective": "Stale context objective"},
            "synthesis": {"key_insights": ["Context insight remains available"]},
            "tags": ["stale"],
        },
        execution_metadata={
            "quality_gates": {
                "research_statement": {"status": "pass"},
                "evidence_links": {"status": "pass"},
                "synthesis_quality": {"status": "pass"},
                "traceability": {"status": "pass"},
                "contradictions_resolved": {"status": "pass"},
            }
        },
        status="completed",
    )
    db_session.add(mission)
    db_session.flush()
    project.mission_protocol_id = mission.id
    document = Document(project_id=project.id, name="Canonical source")
    db_session.add(document)
    db_session.commit()

    service = PreflightService(
        search_service=_RecordingSearch(),
        session_factory=SessionLocal,
        telemetry_enabled=False,
    )
    metadata = service._load_mission_metadata(
        [str(document.id)],
        allowed_project_ids=[project.id],
    )
    match = service._build_single_match(metadata[str(document.id)], 0.95)

    assert match is not None
    assert match.mission_id == "PEDR-CANONICAL"
    assert match.title == "Canonical mission title"
    assert match.objective == "Canonical mission objective"
    assert match.tags == ["canonical"]
    assert match.quality_gates_passed == 5
    assert [insight.text for insight in match.key_insights] == [
        "Context insight remains available"
    ]


def test_preflight_scoped_loader_rejects_cross_project_mission_pointer(db_session):
    """An allowed project cannot attach a denied mission to its documents."""
    allowed_project = Project(name="Allowed metadata project")
    denied_project = Project(name="Denied metadata project")
    db_session.add_all([allowed_project, denied_project])
    db_session.flush()
    denied_mission = Mission(
        project_id=denied_project.id,
        mission_id="PEDR-FOREIGN",
        title="Foreign mission title",
        objective="Foreign mission objective",
        success_criteria=["Remain private"],
        context={"synthesis": {"key_insights": ["Private insight"]}},
        status="completed",
    )
    db_session.add(denied_mission)
    db_session.flush()
    allowed_project.mission_protocol_id = denied_mission.id
    document = Document(project_id=allowed_project.id, name="Allowed source")
    db_session.add(document)
    db_session.commit()

    service = PreflightService(
        search_service=_RecordingSearch(),
        session_factory=SessionLocal,
        telemetry_enabled=False,
    )
    scoped = service._load_mission_metadata(
        [str(document.id)],
        allowed_project_ids=[allowed_project.id],
    )
    unscoped = service._load_mission_metadata([str(document.id)])

    assert scoped[str(document.id)]["mission_uuid"] is None
    assert scoped[str(document.id)]["title"] is None
    assert unscoped[str(document.id)]["mission_uuid"] == str(denied_mission.id)
    assert unscoped[str(document.id)]["title"] == "Foreign mission title"


def test_preflight_none_scope_preserves_legacy_call_shape():
    search = _RecordingSearch()
    service = PreflightService(
        search_service=search,
        session_factory=MagicMock(),
        telemetry_enabled=False,
    )

    recommendation = service.query(PreflightQuery(query="legacy unscoped"))

    assert recommendation.action == "proceed"
    assert "allowed_project_ids" not in search.calls[0]


def test_preflight_service_principal_empty_scope_never_calls_search(db_session, monkeypatch):
    """A SERVICE principal receives proceed without touching hybrid/Qdrant."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    search = _RecordingSearch(
        [{"document_id": str(uuid4()), "score": 0.99, "project_id": str(uuid4())}]
    )
    service = PreflightService(
        search_service=search,
        session_factory=MagicMock(),
        telemetry_enabled=False,
    )
    service_user = _user(role=ROLE_SERVICE)

    recommendation = asyncio.run(
        preflight_query(
            request=PreflightQuery(query="private research"),
            db=db_session,
            current_user=service_user,
            service=service,
            x_agent_id=None,
        )
    )

    assert recommendation.action == "proceed"
    assert recommendation.match_count == 0
    assert recommendation.matches == []
    assert search.calls == []
