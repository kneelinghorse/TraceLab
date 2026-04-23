"""Tests for the submit-time lint gate (T40.3).

Covers every lint rule with positive (fires) + negative (passes) cases, then
integration tests that hit POST /api/v1/missions/{id}/submit and assert the
422 / 200+warnings response shapes.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.mission import Mission
from app.models.project import Project
from app.services.mission_linter import (
    BroadObjectiveNeedsEntities,
    DistributivePhrasingNeedsEntities,
    ExclusionLanguageNeedsExcludedEntities,
    StructuralOutputNeedsShape,
    lint_mission_for_submit,
)


@dataclass
class _MissionStub:
    """Lightweight stand-in for the Mission ORM model when testing rules
    directly. Lets us skip DB setup for pure-regex assertions."""

    title: str = "Test"
    objective: str = "A test objective."
    success_criteria: list[str] | None = None
    deliverables: list[str] | None = None
    required_entities: list[str] | None = None
    excluded_entities: list[str] | None = None
    expected_output_schema: dict[str, Any] | None = None
    background: str | None = None
    focus: str | None = None


# ---------------------------------------------------------------------------
# DistributivePhrasingNeedsEntities
# ---------------------------------------------------------------------------


class TestDistributivePhrasingRule:
    rule = DistributivePhrasingNeedsEntities()

    @pytest.mark.parametrize(
        "criterion",
        [
            "Summarize each competitor's positioning",
            "For every market segment, identify the top 3 players",
            "Document findings per region",
            "For each vertical, compare pricing models",
        ],
    )
    def test_fires_when_distributive_and_no_entities(self, criterion: str):
        mission = _MissionStub(
            title="Analysis",
            objective="Do the thing.",
            success_criteria=[criterion],
        )
        violations = self.rule.check(mission)
        assert len(violations) == 1
        assert violations[0].rule == self.rule.name
        assert violations[0].field == "success_criteria"

    def test_passes_when_required_entities_supplied(self):
        mission = _MissionStub(
            success_criteria=["Summarize each competitor's positioning"],
            required_entities=["Acme Corp", "Globex"],
        )
        assert self.rule.check(mission) == []

    def test_passes_when_two_proper_nouns_present(self):
        mission = _MissionStub(
            title="Benchmarking Tesla and Rivian",
            objective="Compare battery cost per kWh across the two manufacturers.",
            success_criteria=["Summarize each vendor's range claims"],
        )
        assert self.rule.check(mission) == []

    def test_passes_when_no_distributive_phrasing(self):
        mission = _MissionStub(
            success_criteria=["Summarize the top three players"],
        )
        assert self.rule.check(mission) == []


# ---------------------------------------------------------------------------
# StructuralOutputNeedsShape
# ---------------------------------------------------------------------------


class TestStructuralOutputRule:
    rule = StructuralOutputNeedsShape()

    @pytest.mark.parametrize(
        "criterion",
        [
            "Produce an executive summary",
            "Build a comparison table of features",
            "Render the output as a matrix",
            "Deliver as markdown",
            "Include columns for price, latency, and rating",
            "Group findings into sections",
            "Use clear headings",
        ],
    )
    def test_fires_when_structural_output_but_no_shape(self, criterion: str):
        mission = _MissionStub(success_criteria=[criterion])
        violations = self.rule.check(mission)
        assert len(violations) == 1
        assert violations[0].rule == self.rule.name

    def test_passes_when_deliverables_present(self):
        mission = _MissionStub(
            success_criteria=["Produce an executive summary"],
            deliverables=["summary.md"],
        )
        assert self.rule.check(mission) == []

    def test_passes_when_expected_output_schema_present(self):
        mission = _MissionStub(
            success_criteria=["Build a comparison table"],
            expected_output_schema={"type": "object", "properties": {}},
        )
        assert self.rule.check(mission) == []

    def test_empty_expected_output_schema_does_not_satisfy(self):
        """An empty dict is not a real schema."""
        mission = _MissionStub(
            success_criteria=["Build a comparison table"],
            expected_output_schema={},
        )
        assert len(self.rule.check(mission)) == 1

    def test_passes_when_no_structural_terms(self):
        mission = _MissionStub(success_criteria=["Return key insights."])
        assert self.rule.check(mission) == []


# ---------------------------------------------------------------------------
# ExclusionLanguageNeedsExcludedEntities
# ---------------------------------------------------------------------------


class TestExclusionLanguageRule:
    rule = ExclusionLanguageNeedsExcludedEntities()

    @pytest.mark.parametrize(
        "prose_field,text",
        [
            ("objective", "Research enterprise SaaS pricing but exclude consumer apps."),
            ("objective", "Cover the market; ignore products released before 2020."),
            ("background", "We have prior coverage — don't include anything from 2022."),
            ("focus", "Papers without industry funding only."),
            ("objective", "Do not include vendors on the gov-ban list."),
        ],
    )
    def test_fires_when_exclusion_language_but_empty_excluded_entities(
        self, prose_field: str, text: str
    ):
        mission = _MissionStub(**{prose_field: text})
        violations = self.rule.check(mission)
        assert len(violations) == 1
        assert violations[0].field == prose_field

    def test_passes_when_excluded_entities_populated(self):
        mission = _MissionStub(
            objective="Research SaaS; exclude consumer apps.",
            excluded_entities=["consumer apps", "B2C"],
        )
        assert self.rule.check(mission) == []

    def test_passes_when_no_exclusion_language(self):
        mission = _MissionStub(objective="Summarize the enterprise SaaS landscape.")
        assert self.rule.check(mission) == []


# ---------------------------------------------------------------------------
# BroadObjectiveNeedsEntities (soft warning)
# ---------------------------------------------------------------------------


class TestBroadObjectiveRule:
    rule = BroadObjectiveNeedsEntities()

    def test_warns_on_long_objective_with_no_entities(self):
        mission = _MissionStub(
            objective=(
                "write a research report exploring the history and current state "
                "of the relevant market and highlighting opportunities and risks"
            ),
        )
        violations = self.rule.check(mission)
        assert len(violations) == 1
        assert self.rule.severity == "warning"

    def test_skips_short_objective(self):
        mission = _MissionStub(objective="Brief scan.")
        assert self.rule.check(mission) == []

    def test_skips_when_required_entities_present(self):
        mission = _MissionStub(
            objective=(
                "write a long research report about the general market landscape "
                "without targeting any specific company or product for context"
            ),
            required_entities=["Anthropic"],
        )
        assert self.rule.check(mission) == []

    def test_skips_when_proper_nouns_present(self):
        mission = _MissionStub(
            objective=(
                "Analyze the competitive landscape around Anthropic and OpenAI "
                "focusing on developer adoption trends over the past 18 months."
            ),
        )
        assert self.rule.check(mission) == []


# ---------------------------------------------------------------------------
# lint_mission_for_submit — aggregate
# ---------------------------------------------------------------------------


class TestLintAggregate:
    def test_clean_mission_returns_no_findings(self):
        mission = _MissionStub(
            title="Compare CCS vs supervised probing",
            objective="Contrast Contrast-Consistent Search with probing.",
            success_criteria=["Summarize key findings."],
            required_entities=["CCS", "probing"],
        )
        result = lint_mission_for_submit(mission)
        assert result.errors == []
        assert result.warnings == []

    def test_multiple_errors_aggregate(self):
        mission = _MissionStub(
            objective="Research the market but exclude paywalled sources.",
            success_criteria=[
                "Produce an executive summary",
                "Summarize each competitor",
            ],
        )
        result = lint_mission_for_submit(mission)
        rules_fired = {v.rule for v in result.errors}
        assert "distributive-phrasing-needs-entities" in rules_fired
        assert "structural-output-needs-shape" in rules_fired
        assert "exclusion-language-needs-excluded-entities" in rules_fired


# ---------------------------------------------------------------------------
# Integration — POST /missions/{id}/submit
# ---------------------------------------------------------------------------


def _make_project(db_session) -> Project:
    p = Project(name="Linter Project", description="for lint tests")
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _make_mission(db_session, **overrides) -> Mission:
    defaults = dict(
        mission_id=f"LINT-{uuid.uuid4().hex[:6]}",
        title="Reasonable title",
        objective="This mission has a sensible objective that names the targets.",
        success_criteria=["Pass the lint gate."],
        status="draft",
    )
    defaults.update(overrides)
    mission = Mission(**defaults)
    db_session.add(mission)
    db_session.commit()
    db_session.refresh(mission)
    return mission


class TestSubmitEndpointLintIntegration:
    def test_hard_fail_returns_422_with_errors(self, auth_headers, db_session):
        project = _make_project(db_session)
        # Mission that fires distributive + structural rules.
        mission = _make_mission(
            db_session,
            project_id=project.id,
            objective="Generic market research.",
            success_criteria=[
                "Summarize each competitor's positioning",
                "Produce an executive summary",
            ],
        )
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/missions/{mission.id}/submit",
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        rules = {e["rule"] for e in detail["errors"]}
        assert "distributive-phrasing-needs-entities" in rules
        assert "structural-output-needs-shape" in rules
        # Each error has the required envelope shape.
        for err in detail["errors"]:
            assert set(err.keys()) == {"rule", "field", "message", "suggestion"}

    def test_soft_warning_surfaces_but_does_not_block(self, auth_headers, db_session):
        project = _make_project(db_session)
        # Broad long objective with no entities — only the soft rule fires.
        # Keep prose clear of exclusion-language / distributive / structural
        # triggers so we test the warning path in isolation.
        mission = _make_mission(
            db_session,
            project_id=project.id,
            objective=(
                "write a research report exploring broad market landscape "
                "themes and opportunities in the space, with a general "
                "overview tone rather than specific targeting"
            ),
            success_criteria=["Return key insights."],
        )
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/missions/{mission.id}/submit",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "queued"
        rules = {w["rule"] for w in body.get("warnings", [])}
        assert "broad-objective-no-entities" in rules

    def test_clean_mission_submits_with_empty_warnings(self, auth_headers, db_session):
        project = _make_project(db_session)
        mission = _make_mission(
            db_session,
            project_id=project.id,
            objective="Compare Acme Corp against Globex on developer experience.",
            success_criteria=["Return three ranked findings."],
            required_entities=["Acme Corp", "Globex"],
        )
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/missions/{mission.id}/submit",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "queued"
        assert body["warnings"] == []

    def test_hard_fail_preserves_draft_status(self, auth_headers, db_session):
        """The mission must NOT transition to queued on a 422 lint fail."""
        project = _make_project(db_session)
        mission = _make_mission(
            db_session,
            project_id=project.id,
            success_criteria=[
                "Summarize each competitor's positioning",
                "Produce an executive summary",
            ],
        )
        mission_uuid = mission.id
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/missions/{mission_uuid}/submit",
            headers=auth_headers,
        )
        assert resp.status_code == 422

        # Fetch the mission back — status must still be draft.
        get_resp = client.get(
            f"/api/v1/missions/{mission_uuid}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "draft"
