"""Integration tests for the contract-preview endpoint.

T40.4 originally proxied requests over HMAC-signed HTTPS to a DeepSearch
HTTP service that was never deployed in production, returning 502s. T41.1
replaced the round-trip with a local call into the vendored compiler at
``app/services/contract_compiler/``. These tests now exercise the full
local path end-to-end: route → preview client → vendored compiler →
response shaping. No httpx, no signing, no MockTransport — the surface is
entirely in-process.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import missions as missions_routes
from app.main import app
from app.models.mission import Mission
from app.models.project import Project
from app.services import deepsearch_preview_client


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


class TestContractPreviewRoute:
    """End-to-end coverage of GET /api/v1/missions/{id}/contract-preview."""

    def test_happy_path_compiles_locally_and_returns_compiled_contract(
        self, auth_headers, db_session
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

        # Authored required_entities flow through the compiler into
        # named_entities — the regression DS hit on OODS-FIGMA-HOST-01 was
        # exactly this round-trip going dark.
        assert set(body["named_entities"]) >= {"CCS", "probing"}

        # Compiler builds objectives/evidence_slots/acceptance_checks from
        # the mission's success_criteria and authoring fields.
        assert isinstance(body["objectives"], list)
        assert isinstance(body["evidence_slots"], list)
        assert isinstance(body["acceptance_checks"], list)

        # Authored expected_output_schema lands in deliverable_schemas.
        schemas = body["deliverable_schemas"]
        assert isinstance(schemas, list)
        assert len(schemas) >= 1

        # Threshold overrides are passed through unchanged.
        assert body["coverage_thresholds"]["min_sources"] == pytest.approx(12.0)
        assert body["validation_thresholds"]["structural"] == pytest.approx(0.85)

    def test_compiler_rejection_returns_422(
        self, auth_headers, db_session, monkeypatch
    ):
        """Compiler ValueError must surface as 422 with upstream-style detail."""
        from app.services import deepsearch_preview_client as preview_mod

        def boom(mission, *, client=None):
            raise preview_mod.ContractPreviewError(
                "Mission contract preview failed: invalid required_entities",
                status_code=422,
                detail={
                    "error": "Mission contract preview failed",
                    "field": "required_entities",
                    "message": "invalid required_entities",
                },
            )

        monkeypatch.setattr(missions_routes, "_call_deepsearch_preview", boom)

        project = _make_project(db_session)
        mission = _make_mission(db_session, project)

        client = TestClient(app)
        resp = client.get(
            f"/api/v1/missions/{mission.id}/contract-preview",
            headers=auth_headers,
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["upstream_status"] == 422
        assert detail["upstream_detail"]["field"] == "required_entities"

    def test_missing_mission_returns_404(self, auth_headers):
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/missions/{uuid.uuid4()}/contract-preview",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_unexpected_compiler_failure_returns_502(
        self, auth_headers, db_session, monkeypatch
    ):
        """Non-validation exceptions surface as 502 (route's transport-error map)."""
        from app.services import deepsearch_preview_client as preview_mod

        def boom(mission, *, client=None):
            raise preview_mod.ContractPreviewError(
                "Mission contract preview failed: unexpected internal error",
                status_code=None,
                detail=None,
            )

        monkeypatch.setattr(missions_routes, "_call_deepsearch_preview", boom)

        project = _make_project(db_session)
        mission = _make_mission(db_session, project)

        client = TestClient(app)
        resp = client.get(
            f"/api/v1/missions/{mission.id}/contract-preview",
            headers=auth_headers,
        )
        assert resp.status_code == 502

    def test_does_not_mutate_mission_state(
        self, auth_headers, db_session
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


class TestLocalCompileContract:
    """Direct coverage of the preview client without going through the route.

    These prove the contract-guard behaviors that DeepSearch's mock-style
    HTTP tests used to assert (entity passthrough, threshold overrides,
    fallback for legacy constraints) — now hitting the local compiler so
    a regression in the vendored code surfaces as a unit-test failure.
    """

    def test_required_entities_round_trip(self, db_session):
        project = _make_project(db_session)
        mission = _make_mission(
            db_session,
            project,
            required_entities=[
                "AWS Lambda",
                "Google Cloud Run",
                "Vercel Functions",
                "Fly.io",
                "Railway",
            ],
        )
        preview = deepsearch_preview_client.preview_mission_contract(mission)
        for entity in (
            "AWS Lambda",
            "Google Cloud Run",
            "Vercel Functions",
            "Fly.io",
            "Railway",
        ):
            assert entity in preview.named_entities, (
                f"entity '{entity}' was dropped between authored field and "
                f"compiled contract — same regression DS hit on OODS-FIGMA-HOST-01"
            )

    def test_threshold_overrides_pass_through(self, db_session):
        project = _make_project(db_session)
        mission = _make_mission(
            db_session,
            project,
            coverage_thresholds={"min_sources": 25, "min_distinct_domains": 5},
            validation_thresholds={"structural": 0.9},
        )
        preview = deepsearch_preview_client.preview_mission_contract(mission)
        assert preview.coverage_thresholds["min_sources"] == pytest.approx(25.0)
        assert preview.coverage_thresholds["min_distinct_domains"] == pytest.approx(5.0)
        assert preview.validation_thresholds["structural"] == pytest.approx(0.9)

    def test_legacy_constraints_in_context_are_threaded_through(self, db_session):
        """Pre-T40.1 missions stored constraints inside `context`; the build
        helper must still surface them so the compiler treats them as
        constraints just like a column-resident value would."""
        project = _make_project(db_session)
        mission = _make_mission(
            db_session,
            project,
            constraints=None,
            context={"constraints": ["no paywalled sources", "english only"]},
        )
        payload = deepsearch_preview_client.build_mission_context_from_mission(mission)
        assert payload["constraints"] == [
            "no paywalled sources",
            "english only",
        ]

    def test_no_outbound_http_or_signing_attempted(self, db_session, monkeypatch):
        """Regression guard: T41.1's whole point is that no HTTP request
        leaves this process. If a future refactor reintroduces an outbound
        call, this test catches it before deploy."""
        import httpx

        sentinel: list[str] = []

        def fail_send(*args, **kwargs):
            sentinel.append("httpx call attempted")
            raise AssertionError("preview must not make outbound HTTP")

        monkeypatch.setattr(httpx.Client, "send", fail_send)
        monkeypatch.setattr(httpx.Client, "request", fail_send)
        monkeypatch.setattr(httpx.Client, "post", fail_send)

        project = _make_project(db_session)
        mission = _make_mission(db_session, project)

        preview = deepsearch_preview_client.preview_mission_contract(mission)
        assert preview.named_entities  # compiler ran without HTTP
        assert sentinel == []

    def test_client_kwarg_back_compat_is_ignored(self, db_session):
        """The legacy `client=...` kwarg is accepted but ignored — tests and
        callers that still pass it must not break during the cutover."""
        project = _make_project(db_session)
        mission = _make_mission(db_session, project)

        # Passing a sentinel that would explode if used proves it's ignored.
        sentinel = object()
        preview = deepsearch_preview_client.preview_mission_contract(
            mission, client=sentinel
        )
        assert preview.named_entities  # compile still ran
