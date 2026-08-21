"""Live RBAC verification — e2e_prod wrapper (Sprint 47 T47.2).

Skipped by default. To run the role×route matrix against a DEPLOYED API:

    RBAC_VERIFY_BASE_URL=https://api.tracelab.aquex.ai \
    AUTH_USERNAME=<bootstrap-owner> AUTH_PASSWORD=<...> \
    pytest tests/integration/test_e2e_rbac_live.py -m e2e_prod

This is intentionally NOT wired through the normal DB fixtures: tests/conftest.py
refuses a postgresql/rlwy.net DATABASE_URL (conftest.py:22-26), so prod is
unreachable via fixtures BY DESIGN. The harness talks to the deploy over HTTP only,
so this wrapper never touches the local DB guard.

The lockstep tests below always run (no deploy needed) and fail if the harness's
route lists drift from the wired per-id or PEDR/retrieval surfaces.
"""

from __future__ import annotations

import os
import re

import pytest

from scripts.rbac_verify import (
    _LOCAL_ONLY_AUTHZ_ROUTES,
    RbacVerifier,
    _seed_specs,
    pedr1b_scope_routes,
    pedr1c_anon_routes,
    pedr_scope_routes,
    per_id_routes,
)

BASE_URL = os.environ.get("RBAC_VERIFY_BASE_URL")


def test_live_mission_fixture_is_non_runnable():
    """Fail-open submit probes stop at a harmless completed-state precondition."""
    project_id = "00000000-0000-0000-0000-000000000001"
    mission = next(
        spec for spec in _seed_specs("/api/v1") if spec.name == "mission"
    )

    body = mission.make_body({"project": project_id})

    assert body["project_id"] == project_id
    assert body["success_criteria"]
    assert body["status"] == "completed"


def _wired_routes() -> set[tuple[str, str]]:
    """Return effective method/path pairs across eager and lazy FastAPI routers."""
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:  # FastAPI < 0.141 flattens included routes eagerly.
        iter_route_contexts = None

    from app.main import app

    routes = app.routes if iter_route_contexts is None else iter_route_contexts(app.routes)
    return {
        (method.lower(), route.path)
        for route in routes
        for method in getattr(route, "methods", set())
    }


def test_harness_routes_match_wired_per_id_routes():
    """Lockstep guard: the harness's anon-sweep routes MUST equal the wired
    PER_ID_ROUTES, so the harness can never silently fall behind a newly-wired route
    (a new per-id route added without harness coverage is itself an enforcement gap).
    """
    from app.core.config import settings
    from tests.test_rbac_route_enforcement_api import _RID, PER_ID_ROUTES

    assert set(per_id_routes(settings.api_v1_prefix, _RID)) == set(PER_ID_ROUTES)
    assert {
        ("project", "delete", "/projects/{id}?confirm=true")
    } == _LOCAL_ONLY_AUTHZ_ROUTES
    project_spec = next(
        spec for spec in _seed_specs(settings.api_v1_prefix) if spec.name == "project"
    )
    assert (
        "delete",
        f"{settings.api_v1_prefix}/projects/{{id}}?confirm=true",
    ) in project_spec.routes


def test_harness_pedr_scope_routes_match_wired_surface():
    """The deployed matrix must probe all four PEDR-1 route entry points."""
    from app.core.config import settings

    project_id = "00000000-0000-0000-0000-000000000001"
    probed = {(method, path) for method, path, _body in pedr_scope_routes(settings.api_v1_prefix, project_id)}
    wired = _wired_routes()

    assert ("post", f"{settings.api_v1_prefix}/pedr/search") in probed & wired
    assert ("post", f"{settings.api_v1_prefix}/pedr/preflight") in probed & wired
    assert ("post", f"{settings.api_v1_prefix}/retrieval/search") in probed & wired
    assert any(
        method == "get" and path.startswith(f"{settings.api_v1_prefix}/pedr/related/")
        for method, path in probed
    )
    assert ("get", f"{settings.api_v1_prefix}/pedr/related/{{urn:path}}") in wired


def test_harness_pedr1b_scope_routes_match_wired_surface():
    """The deployed matrix must probe all three PEDR-1B entry points."""
    from app.core.config import settings

    project_id = "00000000-0000-0000-0000-000000000001"
    chunk_id = "00000000-0000-0000-0000-000000000002"
    probed = {
        (method, path)
        for method, path, _body in pedr1b_scope_routes(
            settings.api_v1_prefix,
            project_id,
            chunk_id,
        )
    }

    assert probed <= _wired_routes()


def test_harness_pedr1c_routes_match_wired_surface():
    """Every PEDR-1C family route is live-probed or explicitly local-only."""
    from app.core.config import settings

    resource_id = "00000000-0000-0000-0000-000000000001"
    live_probed = {
        (method, path.replace(resource_id, "{id}"))
        for method, path, _body in pedr1c_anon_routes(
            settings.api_v1_prefix,
            resource_id,
        )
    }
    inherited_per_id = {
        (method, path.replace(resource_id, "{id}"))
        for method, path in per_id_routes(settings.api_v1_prefix, resource_id)
        if "/collections/" in path or "/reports/" in path
    }
    local_only = {
        ("delete", f"{settings.api_v1_prefix}/search/history"),
    }
    expected = live_probed | inherited_per_id | local_only | {
        ("post", f"{settings.api_v1_prefix}/synthesize")
    }
    wired = {
        (method, re.sub(r"\{[^}]+\}", "{id}", path))
        for method, path in _wired_routes()
    }
    mission_wired = {
        (method, path)
        for method, path in wired
        if path.startswith(f"{settings.api_v1_prefix}/collections")
        or path.startswith(f"{settings.api_v1_prefix}/reports")
        or path.startswith(f"{settings.api_v1_prefix}/saved-searches")
        or path in {
            f"{settings.api_v1_prefix}/search/history",
            f"{settings.api_v1_prefix}/search/replay/{{id}}",
            f"{settings.api_v1_prefix}/synthesize",
        }
    }

    assert mission_wired == expected


@pytest.mark.e2e_prod
@pytest.mark.skipif(not BASE_URL, reason="set RBAC_VERIFY_BASE_URL to run against a live deploy")
def test_live_rbac_matrix():
    """Run the full role×route matrix against the deployed API; fail on any gap."""
    import httpx

    owner = os.environ.get("AUTH_USERNAME")
    password = os.environ.get("AUTH_PASSWORD")
    assert owner and password, "AUTH_USERNAME / AUTH_PASSWORD required for the live run"
    if "@" not in owner:
        owner = f"{owner}@tracelab.local"

    with httpx.Client(base_url=BASE_URL, timeout=120.0) as http:
        verifier = RbacVerifier(http)
        code = verifier.run(owner, password)

    assert code == 0, "RBAC enforcement gaps:\n" + "\n".join(str(g) for g in verifier.gaps)
