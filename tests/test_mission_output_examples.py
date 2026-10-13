"""Published authoring examples must survive storage and structural preview."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mcp_server.tools.missions import _serialize_mission
from app.models.mission import Mission
from app.models.project import Project

ROOT = Path(__file__).resolve().parents[1]


def _example(source: str) -> dict:
    if source == "tool":
        text = (ROOT / "packages/tracelab-mcp/src/index.ts").read_text()
        match = re.search(
            r"expected_output_schema:\s*\{\s*type: 'object',\s*description: '([^']*)'",
            text,
        )
        assert match, "The shipped tool must document the output descriptor"
        return json.loads(match[1].split("Example: ", 1)[1])
    if source == "ui":
        text = (ROOT / "frontend/src/components/missions/MissionForm.tsx").read_text()
        match = re.search(r"expected_output_schema:\s*\n\s*('(?:[^'\\]|\\.)*')", text)
        assert match, "The visible form placeholder must provide an output example"
        return json.loads(ast.literal_eval(match[1]))
    text = (ROOT / "packages/tracelab-mcp/README.md").read_text()
    match = re.search(
        r"<!-- expected-output-schema-example -->\s*```json\s*(.*?)\s*```",
        text,
        re.DOTALL,
    )
    assert match, "The installed README must provide a compilable output example"
    return json.loads(match[1])


@pytest.mark.parametrize("source", ["tool", "ui", "readme"])
def test_documented_output_example_survives_both_serializers_and_preview(
    source, auth_headers, db_session
):
    descriptor = _example(source)
    project = Project(name="Output example fixture")
    db_session.add(project)
    db_session.commit()
    client = TestClient(app)
    created = client.post(
        "/api/v1/missions",
        headers=auth_headers,
        json={
            "mission_id": f"OUTPUT-{uuid4().hex[:8]}",
            "title": "Documented output example",
            "objective": "Verify the documented descriptor compiles without dispatch.",
            "success_criteria": ["The authored deliverable survives structural preview."],
            "project_id": str(project.id),
            "expected_output_schema": descriptor,
        },
    )
    assert created.status_code == 201, created.text
    mission_id = created.json()["id"]
    stored = client.get(f"/api/v1/missions/{mission_id}", headers=auth_headers)
    assert stored.json()["expected_output_schema"] == descriptor
    mission = db_session.get(Mission, UUID(mission_id))
    assert _serialize_mission(mission)["expected_output_schema"] == descriptor
    preview = client.get(
        f"/api/v1/missions/{mission_id}/contract-preview", headers=auth_headers
    )
    assert preview.status_code == 200, preview.text
    assert any(
        all(schema[key] == descriptor[key] for key in ("kind", "title", "format"))
        and schema["required_sections"] == descriptor["required_sections"]
        for schema in preview.json()["deliverable_schemas"]
    )
    db_session.refresh(mission)
    assert mission.status == "draft"
    assert not mission.deepsearch_job_id
    assert not mission.deepsearch_attempt_count
