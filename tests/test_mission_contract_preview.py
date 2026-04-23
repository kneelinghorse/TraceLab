"""Integration tests for the contract-preview endpoint (T40.4).

Uses httpx.MockTransport to stand in for DeepSearch's preview endpoint so the
tests run hermetically — verifying that TraceLab signs the outbound body,
forwards the full authoring payload, and surfaces the compiled contract back
to the caller without mutating mission state.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.mission import Mission
from app.models.project import Project
from app.services import deepsearch_preview_client
from app.services.deepsearch_hmac_signer import verify_signature

SHARED_SECRET = "test-shared-secret-" + "b" * 45  # 64-char


def _make_project(db_session) -> Project:
    p = Project(name="Preview Project", description="for contract-preview tests")
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _make_mission(db_session, project, **overrides) -> Mission:
    defaults = dict(
        mission_id=f"PREV-{uuid.uuid4().hex[:6]}",
        project_id=project.id,
        title="Contrast-Consistent Search vs supervised probing",
        objective="Compare CCS against supervised probing baselines.",
        success_criteria=["Rank methods by held-out accuracy."],
        status="draft",
        background="CCS (Burns et al. 2022) vs probing literature.",
        focus="Only peer-reviewed benchmarks since 2020.",
        required_entities=["CCS", "probing"],
        expected_output_schema={
            "kind": "comparison-table",
            "title": "Method comparison",
            "format": "markdown",
        },
        coverage_thresholds={"min_sources": 12},
        validation_thresholds={"structural": 0.85},
        deliverable_format="markdown report",
        max_loops=6,
        min_loops=3,
        constraints=["no paywalled sources"],
        references=[{"title": "Burns et al. 2022"}],
    )
    defaults.update(overrides)
    mission = Mission(**defaults)
    db_session.add(mission)
    db_session.commit()
    db_session.refresh(mission)
    return mission


_DEFAULT_UPSTREAM_RESPONSE = {
    "named_entities": ["CCS", "probing"],
    "objectives": [{"text": "Compare CCS against supervised probing baselines."}],
    "evidence_slots": [{"slot": "benchmark-results", "required": True}],
    "acceptance_checks": [{"check": "ranks methods"}],
    "deliverable_schemas": [
        {
            "kind": "comparison-table",
            "title": "Method comparison",
            "format": "markdown",
        }
    ],
    "coverage_thresholds": {"min_sources": 12.0},
    "validation_thresholds": {"structural": 0.85},
}


@pytest.fixture
def mock_upstream(monkeypatch):
    """Install a MockTransport that captures the outbound request and returns
    a canned response. Tests can reach in and assert on what was signed."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        captured["body"] = request.content
        return httpx.Response(200, json=_DEFAULT_UPSTREAM_RESPONSE)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, timeout=5.0)

    # Patch the preview client so it uses our injected httpx client and URL.
    monkeypatch.setattr(
        deepsearch_preview_client,
        "_resolve_preview_url",
        lambda: "https://deepsearch.test/api/v1/missions/preview",
    )

    from app.core import config as config_module

    monkeypatch.setattr(
        config_module.settings,
        "deepsearch_tracelab_service_secret",
        SHARED_SECRET,
        raising=False,
    )

    # Wrap preview_mission_contract so we can thread the mock client in.
    original = deepsearch_preview_client.preview_mission_contract

    def patched(mission, client_override=None):
        return original(mission, client=client)

    monkeypatch.setattr(
        deepsearch_preview_client,
        "preview_mission_contract",
        patched,
    )
    # Also patch the import used inside the route module.
    from app.api.v1 import missions as missions_routes

    monkeypatch.setattr(
        missions_routes,
        "_call_deepsearch_preview",
        patched,
    )

    try:
        yield captured
    finally:
        client.close()


class TestContractPreviewRoute:
    def test_happy_path_forwards_payload_and_returns_compiled_contract(
        self, auth_headers, db_session, mock_upstream
    ):
        project = _make_project(db_session)
        mission = _make_mission(db_session, project)

        client = TestClient(app)
        resp = client.get(
            f"/api/v1/missions/{mission.id}/contract-preview",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["mission_id"] == mission.mission_id
        assert body["mission_uuid"] == str(mission.id)
        assert body["named_entities"] == ["CCS", "probing"]
        assert body["coverage_thresholds"] == {"min_sources": 12.0}

        # The outbound request should have hit the preview URL, carried
        # X-TraceLab-Signature + X-TraceLab-Timestamp headers, and included
        # all authored fields.
        assert mock_upstream["url"] == "https://deepsearch.test/api/v1/missions/preview"
        assert mock_upstream["method"] == "POST"
        assert "x-tracelab-signature" in mock_upstream["headers"]
        assert "x-tracelab-timestamp" in mock_upstream["headers"]

        sent = json.loads(mock_upstream["body"])
        assert sent["mission_id"] == mission.mission_id
        assert sent["background"] == mission.background
        assert sent["required_entities"] == ["CCS", "probing"]
        assert sent["expected_output_schema"]["kind"] == "comparison-table"
        assert sent["max_loops"] == 6

    def test_signature_verifies_round_trip(
        self, auth_headers, db_session, mock_upstream
    ):
        project = _make_project(db_session)
        mission = _make_mission(db_session, project)

        client = TestClient(app)
        resp = client.get(
            f"/api/v1/missions/{mission.id}/contract-preview",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # The body the upstream received plus its signature headers should
        # verify against the shared secret — otherwise DeepSearch would 401.
        assert verify_signature(
            mock_upstream["body"],
            mock_upstream["headers"]["x-tracelab-signature"],
            mock_upstream["headers"]["x-tracelab-timestamp"],
            secret=SHARED_SECRET,
        )

    def test_missing_mission_returns_404(self, auth_headers, mock_upstream):
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/missions/{uuid.uuid4()}/contract-preview",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_upstream_422_surfaces_to_caller(
        self, auth_headers, db_session, monkeypatch
    ):
        """DeepSearch's own compiler errors come back with the same 4xx code."""
        from app.core import config as config_module
        from app.api.v1 import missions as missions_routes
        from app.services import deepsearch_preview_client as preview_mod

        monkeypatch.setattr(
            config_module.settings,
            "deepsearch_tracelab_service_secret",
            SHARED_SECRET,
            raising=False,
        )
        monkeypatch.setattr(
            preview_mod,
            "_resolve_preview_url",
            lambda: "https://deepsearch.test/api/v1/missions/preview",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(422, json={"detail": "compiler rejected"})

        mock_client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)

        def patched(mission, client_override=None):
            return preview_mod.preview_mission_contract(mission, client=mock_client)

        monkeypatch.setattr(missions_routes, "_call_deepsearch_preview", patched)

        project = _make_project(db_session)
        mission = _make_mission(db_session, project)

        try:
            client = TestClient(app)
            resp = client.get(
                f"/api/v1/missions/{mission.id}/contract-preview",
                headers=auth_headers,
            )
            assert resp.status_code == 422
            detail = resp.json()["detail"]
            assert detail["upstream_status"] == 422
            assert detail["upstream_detail"] == {"detail": "compiler rejected"}
        finally:
            mock_client.close()

    def test_upstream_network_failure_returns_502(
        self, auth_headers, db_session, monkeypatch
    ):
        from app.core import config as config_module
        from app.api.v1 import missions as missions_routes
        from app.services import deepsearch_preview_client as preview_mod

        monkeypatch.setattr(
            config_module.settings,
            "deepsearch_tracelab_service_secret",
            SHARED_SECRET,
            raising=False,
        )
        monkeypatch.setattr(
            preview_mod,
            "_resolve_preview_url",
            lambda: "https://deepsearch.test/api/v1/missions/preview",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        mock_client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)

        def patched(mission, client_override=None):
            return preview_mod.preview_mission_contract(mission, client=mock_client)

        monkeypatch.setattr(missions_routes, "_call_deepsearch_preview", patched)

        project = _make_project(db_session)
        mission = _make_mission(db_session, project)

        try:
            client = TestClient(app)
            resp = client.get(
                f"/api/v1/missions/{mission.id}/contract-preview",
                headers=auth_headers,
            )
            assert resp.status_code == 502
        finally:
            mock_client.close()

    def test_does_not_mutate_mission_state(
        self, auth_headers, db_session, mock_upstream
    ):
        project = _make_project(db_session)
        mission = _make_mission(db_session, project)
        mission_uuid = mission.id
        original_status = mission.status

        client = TestClient(app)
        resp = client.get(
            f"/api/v1/missions/{mission_uuid}/contract-preview",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        get = client.get(f"/api/v1/missions/{mission_uuid}", headers=auth_headers)
        assert get.status_code == 200
        assert get.json()["status"] == original_status
