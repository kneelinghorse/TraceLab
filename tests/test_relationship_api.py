"""Tests for the mission relationship context API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.insight import Insight
from app.models.mission_protocol import (
    Evidence,
    MissionProtocolDraft,
    ResearchStatement,
)
from app.services.cache_manager import get_cache_manager
from app.services.mission_protocol_service import MissionProtocolService


@pytest.fixture(autouse=True)
def clear_relationship_cache():
    cache = get_cache_manager()
    cache.invalidate_relationship_context()
    yield
    cache.invalidate_relationship_context()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def relationship_data(db_session, project) -> dict[str, str]:
    document = Document(
        project_id=project.id,
        name="Interview A",
        file_type="transcript",
        source_type="interview",
        content="Ops team insights",
        processed=True,
        chunked=True,
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=12,
        content="Participants highlight workflow friction across finance and ops",
        content_tsv="Participants highlight workflow friction across finance and ops",
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)

    insight = Insight(
        project_id=project.id,
        title="Ops friction",
        content="Workflow blockers increase cycle time",
        insight_type="finding",
        validated=True,
    )
    db_session.add(insight)
    db_session.commit()
    db_session.refresh(insight)

    service = MissionProtocolService()
    draft = MissionProtocolDraft(
        mission_id="REL-PRIMARY",
        title="Relationship Mission",
        project_id=str(project.id),
        research_statement=ResearchStatement(
            topic="Ops", objective="Diagnose friction", scope="Finance"
        ),
        evidence=[
            Evidence(
                evidence_id="EV-1",
                source="Interview A",
                summary="Ops + finance teams sharing the same blockers",
                chunk_id=str(chunk.id),
                insight_id=str(insight.id),
                relevance_score=0.82,
            )
        ],
    )
    mission = service.create_mission_from_draft(
        db_session, project_id=project.id, draft=draft
    )

    peer_draft = MissionProtocolDraft(
        mission_id="REL-PEER",
        title="Peer Mission",
        project_id=str(project.id),
        research_statement=ResearchStatement(
            topic="Ops", objective="Map peers", scope="Finance"
        ),
        evidence=[
            Evidence(
                evidence_id="EV-2",
                source="Interview A",
                summary="Peer mission referencing same sources",
                chunk_id=str(chunk.id),
                relevance_score=0.5,
            )
        ],
    )
    peer_mission = service.create_mission_from_draft(
        db_session, project_id=project.id, draft=peer_draft
    )

    return {
        "mission_id": str(mission.id),
        "peer_id": str(peer_mission.id),
        "chunk_text": chunk.content,
        "document_name": document.name,
        "insight_title": insight.title,
    }


def test_relationship_endpoint_returns_related_entities(
    client: TestClient, auth_headers, relationship_data
):
    response = client.get(
        f"/api/v1/missions/{relationship_data['mission_id']}/related",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["totals"]["documents"] == 1
    assert payload["totals"]["insights"] == 1
    assert payload["totals"]["chunks"] == 1
    assert payload["totals"]["missions"] == 1

    assert payload["documents"][0]["name"] == relationship_data["document_name"]
    assert payload["insights"][0]["title"] == relationship_data["insight_title"]
    assert payload["chunks"][0]["document_name"] == relationship_data["document_name"]
    assert payload["chunks"][0]["preview"] is None  # depth defaults to 1
    assert payload["related_missions"][0]["mission_identifier"] == "REL-PEER"


def test_relationship_endpoint_supports_depth_and_filters(
    client: TestClient, auth_headers, relationship_data
):
    response = client.get(
        f"/api/v1/missions/{relationship_data['mission_id']}/related",
        params={
            "depth": 2,
            "entity_types": ["chunks"],
            "min_relevance": 0.5,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["documents"] == []
    assert payload["insights"] == []
    assert payload["related_missions"] == []
    assert len(payload["chunks"]) == 1
    assert payload["chunks"][0]["preview"].startswith("Participants highlight")


def test_relationship_endpoint_respects_min_relevance_and_cache(
    client: TestClient, auth_headers, relationship_data
):
    first = client.get(
        f"/api/v1/missions/{relationship_data['mission_id']}/related",
        params={"min_relevance": 0.9},
        headers=auth_headers,
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["documents"] == []
    assert first_payload["insights"] == []
    assert first_payload["chunks"] == []
    assert first_payload["cached"] is False

    second = client.get(
        f"/api/v1/missions/{relationship_data['mission_id']}/related",
        params={"min_relevance": 0.9},
        headers=auth_headers,
    )
    assert second.status_code == 200
    assert second.json()["cached"] is True
