"""Local verification of the live RBAC harness logic (Sprint 47 T47.2).

The live harness (scripts/rbac_verify.py) is meant to run against a deployed API,
which CI cannot reach. These tests run it against the in-process app via a
``TestClient`` (the harness is transport-agnostic) to prove its logic is sound BEFORE
it is pointed at prod (the live prod run itself is T47.6):

  * it PASSES against a correctly-enforced app (rbac_enabled=True) — no false gaps;
  * it ABORTS LOUD at the precheck when RBAC is OFF — a flag-off deploy cannot
    silently pass the matrix at 200;
  * it FLAGS a 2xx BOLA leak when a non-owner reaches a resource — so the harness
    itself fails when enforcement breaks (a harness that can't go red is worthless).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import ROLE_OWNER
from app.main import app
from app.models.user import User
from scripts.rbac_verify import (
    _THROWAWAY_PASSWORD,
    HarnessError,
    RbacVerifier,
    _seed_specs,
    pedr1b_scope_routes,
    pedr_scope_routes,
)

OWNER_EMAIL = "tracelab-admin@tracelab.local"  # conftest seed: {AUTH_USERNAME}@tracelab.local
OWNER_PW = "changeme"  # conftest AUTH_PASSWORD


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def owner_principal(db_session):
    """Promote the seeded bootstrap user to OWNER so the harness can mint a second
    owner (POST /admin/users role=owner is owner-gated)."""
    user = db_session.query(User).filter(User.email == OWNER_EMAIL).first()
    assert user is not None, "conftest seed user missing"
    user.role = ROLE_OWNER
    db_session.commit()
    return user


def test_harness_passes_against_enforced_app(client, owner_principal, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    monkeypatch.setattr(
        RbacVerifier,
        "_discover_pedr_search_project",
        lambda _self, _owner_token: str(uuid4()),
    )
    monkeypatch.setattr(
        RbacVerifier,
        "_note_owner_preflight_baseline",
        lambda _self, _owner_token: None,
    )
    monkeypatch.setattr(
        RbacVerifier,
        "_discover_pedr1b_fixture",
        lambda _self, _owner_token: (str(uuid4()), str(uuid4())),
    )
    verifier = RbacVerifier(client)
    code = verifier.run(OWNER_EMAIL, OWNER_PW)
    leaks = [g for g in verifier.gaps if g.kind == "DENY-LEAK-2xx"]
    assert not leaks, f"unexpected BOLA leaks: {[str(g) for g in leaks]}"
    assert code == 0, f"gaps: {[str(g) for g in verifier.gaps]}\nnotes: {verifier.notes}"


def test_precheck_aborts_when_rbac_off(client, owner_principal, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", False)
    verifier = RbacVerifier(client)
    with pytest.raises(HarnessError, match="RBAC IS OFF"):
        verifier.run(OWNER_EMAIL, OWNER_PW)


def test_matrix_flags_leak_when_unenforced(client, owner_principal, monkeypatch):
    """With RBAC OFF a member reaches the resource (200) — the harness MUST flag it.

    Drives the steps directly (bypassing the precheck, which would abort first) to
    prove seeded_matrix records the DENY-LEAK when enforcement is absent."""
    monkeypatch.setattr(settings, "rbac_enabled", False)
    verifier = RbacVerifier(client)
    owner_token = verifier.login(OWNER_EMAIL, OWNER_PW)
    owner_key, _ = verifier.mint_api_key(owner_token)
    created = verifier.create_throwaway_user(owner_key, "member", "leaktest")
    assert created is not None, "member provisioning failed"
    _uid, member_email = created
    member_jwt = verifier.login(member_email, _THROWAWAY_PASSWORD)
    spec = next(s for s in _seed_specs(settings.api_v1_prefix) if s.name == "project")
    rid = verifier.seed(owner_key, spec, {})
    assert rid is not None, "project seeding failed"

    verifier.seeded_matrix(spec, rid, {"member": member_jwt})

    leaks = [g for g in verifier.gaps if g.kind == "DENY-LEAK-2xx"]
    assert leaks, "harness FAILED to flag a 2xx BOLA leak when RBAC was off"


def test_service_log_matrix_flags_leak_when_gate_off(client, owner_principal, monkeypatch):
    """With RBAC OFF the service gate is a no-op, so a non-service human reaches the
    log-write (201). The new service_log_write_matrix MUST flag that as a DENY-LEAK —
    proving the check can go RED (a harness check that can't fail is worthless, the
    T47.2 review lesson). With the flag ON the full run (above) proves it stays green."""
    monkeypatch.setattr(settings, "rbac_enabled", False)
    verifier = RbacVerifier(client)
    owner_token = verifier.login(OWNER_EMAIL, OWNER_PW)
    owner_key, _ = verifier.mint_api_key(owner_token)
    created = verifier.create_throwaway_user(owner_key, "member", "svc-leaktest")
    assert created is not None, "member provisioning failed"
    _uid, member_email = created
    member_jwt = verifier.login(member_email, _THROWAWAY_PASSWORD)
    proj_spec = next(s for s in _seed_specs(settings.api_v1_prefix) if s.name == "project")
    mission_spec = next(s for s in _seed_specs(settings.api_v1_prefix) if s.name == "mission")
    proj_id = verifier.seed(owner_key, proj_spec, {})
    assert proj_id is not None, "project seeding failed"
    mid = verifier.seed(owner_key, mission_spec, {"project": proj_id})
    assert mid is not None, "mission seeding failed"

    verifier.service_log_write_matrix(mid, {"member": member_jwt})

    leaks = [g for g in verifier.gaps if g.kind == "DENY-LEAK-2xx"]
    assert leaks, "harness FAILED to flag the log-write leak when the service gate was off"


def test_service_log_matrix_flags_missing_service_principal(client, owner_principal, monkeypatch):
    """The service-ALLOW probe is the over-block guard the rbac_enabled flip relies on
    (proves the legitimate runner is not denied). If the service principal can't be
    provisioned the harness must go RED (NO-SERVICE-PRINCIPAL), not silently green —
    the asymmetric soft-fail the T47.4 adversarial review caught. The gate runs first,
    so a random mission id is fine: a human is denied (403) before the lookup."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    verifier = RbacVerifier(client)
    owner_token = verifier.login(OWNER_EMAIL, OWNER_PW)
    owner_key, _ = verifier.mint_api_key(owner_token)
    created = verifier.create_throwaway_user(owner_key, "member", "no-svc")
    assert created is not None, "member provisioning failed"
    _uid, member_email = created
    member_jwt = verifier.login(member_email, _THROWAWAY_PASSWORD)

    # A human IS present (deny half runs) but NO service principal is supplied.
    verifier.service_log_write_matrix(str(uuid4()), {"member": member_jwt})

    assert any(g.kind == "NO-SERVICE-PRINCIPAL" for g in verifier.gaps), (
        "harness FAILED to flag the missing service principal (the allow half soft-failed)"
    )


def test_seed_skips_gracefully_when_dependency_missing(client, owner_principal, monkeypatch):
    """seed() must NOT crash (KeyError) when a dependency seed failed: the mission
    spec reads ctx['project']; with an empty ctx it records a note and returns None
    instead of an unhandled exception that would abort before report()."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    verifier = RbacVerifier(client)
    owner_token = verifier.login(OWNER_EMAIL, OWNER_PW)
    owner_key, _ = verifier.mint_api_key(owner_token)
    mission_spec = next(s for s in _seed_specs(settings.api_v1_prefix) if s.name == "mission")

    rid = verifier.seed(owner_key, mission_spec, {})  # ctx has no "project"

    assert rid is None
    assert any("missing dependency" in n for n in verifier.notes)


def test_coverage_accounts_for_every_wired_route():
    """Every wired per-id route is either in the seeded authz matrix or the explicit
    anon-only allowlist — so the harness can never report PASS while a route's authz
    is entirely untested (drift guard against a newly-wired route)."""
    verifier = RbacVerifier(None)  # check_coverage is pure set math, no HTTP
    verifier.check_coverage()
    unaccounted = [g for g in verifier.gaps if g.kind == "UNACCOUNTED-ROUTE"]
    assert not unaccounted, f"routes neither seeded nor anon-only: {[str(g) for g in unaccounted]}"


def test_pedr_scope_routes_cover_exact_mission_surface():
    """PEDR-1 keeps its four route probes separate from the per-id route registry."""
    project_id = str(uuid4())
    routes = pedr_scope_routes("/api/v1", project_id)

    assert [(method, path) for method, path, _body in routes] == [
        ("post", "/api/v1/pedr/search"),
        ("get", f"/api/v1/pedr/related/urn:research:project:{project_id}"),
        ("post", "/api/v1/pedr/preflight"),
        ("post", "/api/v1/retrieval/search"),
    ]
    assert routes[0][2]["project_id"] == project_id
    assert routes[3][2]["project_id"] == project_id


def test_pedr1b_scope_routes_cover_exact_mission_surface():
    """PEDR-1B adds the RAG, synthesis, and facet probes as one unit."""
    project_id = str(uuid4())
    chunk_id = str(uuid4())

    routes = pedr1b_scope_routes("/api/v1", project_id, chunk_id)

    assert [(method, path) for method, path, _body in routes] == [
        ("post", "/api/v1/search"),
        ("post", "/api/v1/synthesize"),
        ("post", "/api/v1/facets"),
    ]
    assert routes[0][2]["project_id"] == project_id
    assert routes[1][2]["chunk_ids"] == [chunk_id]
    assert routes[2][2]["project_id"] == project_id


class _StubResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _LeakyPedrTransport:
    """Return one related 2xx and one search row to prove both guards go red."""

    search_project_id = str(uuid4())

    def __init__(self, *, malformed_member_search: bool = False):
        self.malformed_member_search = malformed_member_search

    def request(self, method, path, *, headers, json):
        if "/pedr/related/" in path:
            return _StubResponse(200, {"related_entities": []})
        if path.endswith("/pedr/search"):
            if (
                self.malformed_member_search
                and headers.get("Authorization") == "Bearer member-jwt"
            ):
                return _StubResponse(200, {"results": "not-a-list"})
            return _StubResponse(200, {"results": [{"project_id": json["project_id"]}]})
        if path.endswith("/pedr/preflight"):
            return _StubResponse(200, {"action": "proceed", "match_count": 0, "matches": []})
        if path.endswith("/retrieval/search"):
            project_id = json.get("project_id") or self.search_project_id
            return _StubResponse(200, {"results": [{"project_id": project_id}]})
        raise AssertionError(f"unexpected probe: {method} {path} {headers}")


class _WrongRelatedStatusTransport:
    """Keep search probes clean while returning a broken related-route denial."""

    def __init__(self, related_status: int):
        self.related_status = related_status

    def request(self, method, path, *, headers, json):
        if "/pedr/related/" in path:
            return _StubResponse(self.related_status, {})
        if path.endswith("/pedr/preflight"):
            return _StubResponse(
                200,
                {"action": "proceed", "match_count": 0, "matches": []},
            )
        if path.endswith(("/pedr/search", "/retrieval/search")):
            return _StubResponse(200, {"results": []})
        raise AssertionError(f"unexpected probe: {method} {path} {headers} {json}")


class _NoSearchFixtureTransport:
    """Owner discovery is empty; no deny probe may fall back to the seeded project."""

    def __init__(self):
        self.explicit_search_calls = 0

    def request(self, method, path, *, headers, json):
        if "/pedr/related/" in path:
            status_code = (
                200
                if headers.get("Authorization") == "Bearer owner-jwt"
                else 403
            )
            return _StubResponse(status_code, {"related_entities": []})
        if path.endswith("/pedr/preflight"):
            return _StubResponse(
                200,
                {"action": "proceed", "match_count": 0, "matches": []},
            )
        if path.endswith("/retrieval/search") and json.get("project_id") is None:
            return _StubResponse(200, {"results": []})
        if path.endswith(("/pedr/search", "/retrieval/search")):
            self.explicit_search_calls += 1
            raise AssertionError("empty fixture discovery must not run deny probes")
        raise AssertionError(f"unexpected probe: {method} {path} {headers} {json}")


def test_pedr_scope_matrix_flags_related_and_search_leaks():
    """The deployed harness must fail on either a root-resource or result-row leak."""
    verifier = RbacVerifier(_LeakyPedrTransport())
    verifier.pedr_scope_matrix(str(uuid4()), {"member": "member-jwt", "owner": "owner-jwt"})

    assert any(g.kind == "DENY-LEAK-2xx" and g.role == "member" for g in verifier.gaps)
    assert any(
        g.kind == "PEDR-SCOPE-LEAK" and g.role == "member" and g.path.endswith("/pedr/search")
        for g in verifier.gaps
    )
    assert any(
        g.kind == "PEDR-SCOPE-LEAK"
        and g.role == "member"
        and g.path.endswith("/retrieval/search")
        for g in verifier.gaps
    )
    assert not any(g.kind == "NO-SEARCHABLE-PROJECT" for g in verifier.gaps)
    assert not any(g.kind == "owner-overblock" for g in verifier.gaps)


def test_pedr_scope_matrix_rejects_malformed_empty_search_shape():
    """A malformed response cannot be mistaken for a correctly scoped empty list."""
    verifier = RbacVerifier(
        _LeakyPedrTransport(malformed_member_search=True),
        log=lambda _message: None,
    )

    verifier.pedr_scope_matrix(
        str(uuid4()),
        {"member": "member-jwt", "owner": "owner-jwt"},
    )

    assert any(
        gap.kind == "PEDR-SCOPE-SHAPE"
        and gap.path.endswith("/pedr/search")
        for gap in verifier.gaps
    )


@pytest.mark.parametrize("status_code", [404, 500])
def test_pedr_scope_matrix_requires_exact_related_403(status_code):
    """A broken/nonexistent related path is not proof of authorization denial."""
    verifier = RbacVerifier(
        _WrongRelatedStatusTransport(status_code),
        log=lambda _message: None,
    )

    verifier.pedr_scope_matrix(str(uuid4()), {"member": "member-jwt"})

    assert any(
        gap.kind == "PEDR-RELATED-STATUS"
        and gap.expected == "403"
        and gap.actual == str(status_code)
        for gap in verifier.gaps
    )
    assert verifier.report() == 1


def test_pedr_scope_matrix_fails_when_no_known_positive_search_project_exists():
    """An empty seeded project cannot masquerade as live search-isolation proof."""
    transport = _NoSearchFixtureTransport()
    verifier = RbacVerifier(transport, log=lambda _message: None)

    verifier.pedr_scope_matrix(
        str(uuid4()),
        {"member": "member-jwt", "owner": "owner-jwt"},
    )

    assert any(gap.kind == "NO-SEARCHABLE-PROJECT" for gap in verifier.gaps)
    assert transport.explicit_search_calls == 0
    assert any("smoke only" in note for note in verifier.notes)
    assert verifier.report() == 1


class _LeakyPedr1bTransport:
    """Hide foreign content behind otherwise-empty metadata for deny callers."""

    project_id = str(uuid4())
    chunk_id = str(uuid4())

    def request(self, method, path, *, headers, json):
        is_owner = headers.get("Authorization") == "Bearer owner-jwt"
        if path.endswith("/retrieval/search"):
            return _StubResponse(
                200,
                {
                    "results": [
                        {
                            "project_id": self.project_id,
                            "chunk_id": self.chunk_id,
                        }
                    ]
                },
            )
        if path.endswith("/search"):
            return _StubResponse(
                200,
                {
                    "answer": "foreign content",
                    "sources": (
                        [{"project_id": self.project_id}] if is_owner else []
                    ),
                    "citations": (
                        [{"chunk_id": self.chunk_id}] if is_owner else []
                    ),
                },
            )
        if path.endswith("/synthesize"):
            return _StubResponse(
                200,
                {
                    "content": "foreign content",
                    "citations": (
                        [{"chunk_id": self.chunk_id}] if is_owner else []
                    ),
                    "chunk_count": 1 if is_owner else 0,
                },
            )
        if path.endswith("/facets"):
            return _StubResponse(
                200,
                {
                    "projects": (
                        [
                            {
                                "value": self.project_id,
                                "label": "foreign project",
                                "count": 1,
                            }
                        ]
                        if is_owner
                        else []
                    ),
                    "document_types": (
                        []
                        if is_owner
                        else [{"value": "secret", "label": "secret", "count": 1}]
                    ),
                    "source_types": [],
                    "tags": [],
                    "date_range": {"min": None, "max": None},
                },
            )
        if path.endswith("/projects?page_size=100"):
            return _StubResponse(200, {"data": []})
        raise AssertionError(f"unexpected probe: {method} {path} {headers} {json}")


class _NoPedr1bFixtureTransport:
    """Return no owner corpus and reject any accidental deny probe."""

    def __init__(self):
        self.calls = 0

    def request(self, method, path, *, headers, json):
        self.calls += 1
        if path.endswith("/retrieval/search"):
            return _StubResponse(200, {"results": []})
        raise AssertionError(f"fixture failure must stop probes: {method} {path}")


def test_pedr1b_scope_matrix_flags_rag_synthesis_and_facet_leaks():
    """Every PEDR-1B live assertion must fail against a leaky transport."""
    verifier = RbacVerifier(_LeakyPedr1bTransport(), log=lambda _message: None)

    verifier.pedr1b_scope_matrix(
        {"owner": "owner-jwt", "member": "member-jwt"}
    )

    assert any(gap.kind == "RAG-SCOPE-LEAK" for gap in verifier.gaps)
    assert any(gap.kind == "SYNTHESIS-SCOPE-LEAK" for gap in verifier.gaps)
    assert any(gap.kind == "FACET-SCOPE-LEAK" for gap in verifier.gaps)
    assert not any(gap.kind == "NO-PEDR1B-FIXTURE" for gap in verifier.gaps)
    assert verifier.report() == 1


def test_pedr1b_scope_matrix_fails_without_owner_positive_fixture():
    """An empty production corpus cannot make tenant-isolation probes vacuous."""
    transport = _NoPedr1bFixtureTransport()
    verifier = RbacVerifier(transport, log=lambda _message: None)

    verifier.pedr1b_scope_matrix(
        {"owner": "owner-jwt", "member": "member-jwt"}
    )

    assert any(gap.kind == "NO-PEDR1B-FIXTURE" for gap in verifier.gaps)
    assert transport.calls == 1
    assert verifier.report() == 1


def test_pedr1b_anon_sweep_can_detect_a_public_route():
    """The new anonymous gate must go red when even one route returns 2xx."""

    class _Transport:
        def request(self, method, path, *, headers, json):
            status_code = 200 if path.endswith("/facets") else 401
            return _StubResponse(status_code, {})

    verifier = RbacVerifier(_Transport(), log=lambda _message: None)

    verifier.pedr1b_anon_sweep()

    assert any(
        gap.kind == "anon-401" and gap.path.endswith("/facets")
        for gap in verifier.gaps
    )
