"""Validates the generated OpenAPI schema for documentation completeness."""

from __future__ import annotations

from app.main import app


def test_openapi_schema_exposes_mission_and_quality_routes():
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/v1/missions" in paths
    assert "/api/v1/missions/create-and-submit" in paths
    assert "/api/v1/missions/{mission_id}/quality" in paths

    mission_ops = paths["/api/v1/missions"]
    assert "get" in mission_ops and "post" in mission_ops
    assert mission_ops["get"].get("summary") is not None
    assert mission_ops["post"].get("responses")


def test_openapi_metadata_highlights_docs_suite():
    schema = app.openapi()
    assert "TraceLab" in schema["info"]["title"]
    assert schema["info"].get("version")
    assert schema["info"].get("description")
