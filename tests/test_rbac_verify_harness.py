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

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import (
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_VIEWER,
    create_access_token,
)
from app.main import app
from app.models.api_key import APIKey
from app.models.chunk import DocumentChunk
from app.models.collection import Collection
from app.models.document import Document
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report
from app.models.saved_search import SavedSearch
from app.models.search_history import SearchHistory
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import Workspace
from app.services.cache_manager import get_cache_manager
from scripts.rbac_verify import (
    _PEDR_SCOPE_QUERY,
    _RAG_EMPTY_ANSWER,
    _SYNTHESIS_EMPTY_CONTENT,
    _THROWAWAY_PASSWORD,
    HarnessError,
    RbacVerifier,
    _seed_specs,
    pedr1b_scope_routes,
    pedr1c_anon_routes,
    pedr_scope_routes,
)

OWNER_EMAIL = "tracelab-admin@tracelab.local"  # conftest seed: {AUTH_USERNAME}@tracelab.local
OWNER_PW = "changeme"  # conftest AUTH_PASSWORD
_SECOND_OWNER_TOKEN = "second-owner-jwt"  # noqa: S105 - fake transport credential
_SECOND_OWNER_ID = str(uuid4())
_MEMBER_ID = str(uuid4())
_VIEWER_ID = str(uuid4())


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


def test_harness_passes_against_enforced_app(
    client,
    db_session,
    owner_principal,
    monkeypatch,
):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    owner_space = Workspace(name=f"harness-owner-{uuid4().hex[:8]}")
    db_session.add(owner_space)
    db_session.flush()
    db_session.add(
        Project(
            name=f"Harness existing owner project {uuid4().hex[:8]}",
            owner_id=owner_principal.id,
            workspace_id=owner_space.id,
        )
    )
    db_session.commit()
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
    pedr1c_calls = []
    monkeypatch.setattr(
        RbacVerifier,
        "pedr1c_scope_matrix",
        lambda _self, principals, _principal_ids=None: pedr1c_calls.append(principals),
    )
    verifier = RbacVerifier(client)
    login_calls = []
    real_login = verifier.login

    def _tracked_login(email, password):
        login_calls.append((email, password))
        return real_login(email, password)

    monkeypatch.setattr(verifier, "login", _tracked_login)
    code = verifier.run(OWNER_EMAIL, OWNER_PW)
    leaks = [g for g in verifier.gaps if g.kind == "DENY-LEAK-2xx"]
    assert not leaks, f"unexpected BOLA leaks: {[str(g) for g in leaks]}"
    assert code == 0, f"gaps: {[str(g) for g in verifier.gaps]}\nnotes: {verifier.notes}"
    assert pedr1c_calls, "run() skipped the PEDR-1C matrix"
    assert len(login_calls) == 5, "live harness must stay within the five-login/minute budget"
    assert set(verifier._principal_ids) == {
        "member",
        "viewer",
        "second_owner",
        "service",
    }


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


def test_service_log_matrix_requires_exact_human_403():
    """A 404/422/5xx human response is not proof that the service gate ran."""

    class _Transport:
        def request(self, method, path, *, headers, json):
            token = headers.get("Authorization")
            if token is None:
                return _StubResponse(401, {})
            if token == "Bearer service-jwt":  # noqa: S105 - fake credential
                return _StubResponse(201, {})
            return _StubResponse(404, {})

    verifier = RbacVerifier(_Transport(), log=lambda _message: None)

    verifier.service_log_write_matrix(
        str(uuid4()),
        {"member": "member-jwt", "service": "service-jwt"},
    )

    assert any(
        gap.kind == "SERVICE-LOG-AUTHZ-STATUS"
        and gap.role == "member"
        and gap.expected == "403"
        and gap.actual == "404"
        for gap in verifier.gaps
    )


def test_required_seed_failure_is_a_hard_gap(client, owner_principal, monkeypatch):
    """A missing required dependency cannot silently skip an authz matrix."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    verifier = RbacVerifier(client)
    owner_token = verifier.login(OWNER_EMAIL, OWNER_PW)
    owner_key, _ = verifier.mint_api_key(owner_token)
    mission_spec = next(s for s in _seed_specs(settings.api_v1_prefix) if s.name == "mission")

    rid = verifier.seed(owner_key, mission_spec, {})  # ctx has no "project"

    assert rid is None
    assert any(gap.kind == "REQUIRED-SEED-FAILURE" for gap in verifier.gaps)
    assert verifier.report() == 1


def test_seeded_mission_cannot_queue_if_authorization_fails_open(
    client,
    db_session,
    owner_principal,
    monkeypatch,
):
    """The live deny probe must stay harmless under the exact bug it detects.

    With RBAC disabled, the member reaches submit past authorize(). The completed
    fixture must fail the submission-state precondition and remain unqueued.
    """
    monkeypatch.setattr(settings, "rbac_enabled", False)
    verifier = RbacVerifier(client, log=lambda _message: None)
    owner_token = verifier.login(OWNER_EMAIL, OWNER_PW)
    owner_key, _key_id = verifier.mint_api_key(owner_token)
    created = verifier.create_throwaway_user(owner_key, "member", "safe-submit")
    assert created is not None
    _member_id, member_email = created
    member_token = verifier.login(member_email, _THROWAWAY_PASSWORD)

    project_spec = next(
        spec for spec in _seed_specs(settings.api_v1_prefix) if spec.name == "project"
    )
    mission_spec = next(
        spec for spec in _seed_specs(settings.api_v1_prefix) if spec.name == "mission"
    )
    project_id = verifier.seed(owner_key, project_spec, {})
    assert project_id is not None
    mission_id = verifier.seed(owner_key, mission_spec, {"project": project_id})
    assert mission_id is not None
    dispatch_calls = []

    def _unexpected_queue_update(*args, **kwargs):
        dispatch_calls.append((args, kwargs))
        raise AssertionError("completed verifier fixture reached queue update")

    monkeypatch.setattr(
        "app.api.v1.missions._service.update_mission",
        _unexpected_queue_update,
    )

    response = client.post(
        f"{settings.api_v1_prefix}/missions/{mission_id}/submit",
        headers={"Authorization": f"Bearer {member_token}"},
    )

    assert response.status_code == 400
    db_session.expire_all()
    mission = db_session.get(Mission, mission_id)
    assert mission is not None
    assert mission.status == "completed"
    assert dispatch_calls == []


def test_seeded_matrix_requires_exact_403_with_valid_mutation_body():
    """422/404/5xx are harness gaps, and child probes use a schema-valid UUID."""

    class _WrongStatusTransport:
        def __init__(self):
            self.calls = []

        def request(self, method, path, *, headers, json):
            self.calls.append((method, path, headers, json))
            return _StubResponse(422, {})

    transport = _WrongStatusTransport()
    verifier = RbacVerifier(transport, log=lambda _message: None)
    spec = next(
        item for item in _seed_specs("/api/v1") if item.name == "collection"
    )

    verifier.seeded_matrix(
        spec,
        str(uuid4()),
        {"member": "member-jwt", "viewer": "viewer-jwt"},
    )

    assert len(verifier.gaps) == len(spec.routes) * 2
    assert {gap.kind for gap in verifier.gaps} == {"COLLECTION-AUTHZ-STATUS"}
    child_bodies = [
        body
        for method, path, _headers, body in transport.calls
        if method == "POST" and path.endswith("/chunks")
    ]
    assert len(child_bodies) == 2
    assert all(str(UUID(body["chunk_id"])) == body["chunk_id"] for body in child_bodies)


def test_project_delete_authz_is_local_only_but_still_covered():
    """The deployed matrix never tombstones a project; local coverage keeps DELETE."""

    class _DenyTransport:
        def __init__(self):
            self.calls = []

        def request(self, method, path, *, headers, json):
            self.calls.append((method, path, headers, json))
            return _StubResponse(403, {})

    spec = next(
        item for item in _seed_specs("/api/v1") if item.name == "project"
    )
    resource_id = str(uuid4())
    principals = {"member": "member-jwt", "viewer": "viewer-jwt"}
    local_transport = _DenyTransport()
    live_transport = _DenyTransport()

    RbacVerifier(local_transport, log=lambda _message: None).seeded_matrix(
        spec,
        resource_id,
        principals,
    )
    RbacVerifier(live_transport, log=lambda _message: None).seeded_matrix(
        spec,
        resource_id,
        principals,
        live_safe=True,
    )

    assert sum(method == "DELETE" for method, *_rest in local_transport.calls) == 2
    assert all(method != "DELETE" for method, *_rest in live_transport.calls)
    assert len(live_transport.calls) == (len(spec.routes) - 1) * 2


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


def test_pedr1c_anon_routes_cover_exact_alternate_surface():
    """PEDR-1C locks authentication coverage for every alternate artifact route."""
    resource_id = str(uuid4())

    routes = pedr1c_anon_routes("/api/v1", resource_id)

    assert [(method, path) for method, path, _body in routes] == [
        ("get", "/api/v1/collections"),
        ("post", "/api/v1/collections"),
        ("get", "/api/v1/saved-searches"),
        ("post", "/api/v1/saved-searches"),
        ("put", f"/api/v1/saved-searches/{resource_id}"),
        ("delete", f"/api/v1/saved-searches/{resource_id}"),
        ("post", f"/api/v1/saved-searches/{resource_id}/execute"),
        ("get", "/api/v1/search/history"),
        ("post", f"/api/v1/search/replay/{resource_id}"),
        ("get", "/api/v1/reports"),
        ("post", "/api/v1/reports"),
    ]


class _StubResponse:
    def __init__(self, status_code, payload, *, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else str(payload)

    def json(self):
        return self._payload


class _ForwardingFaultTransport:
    """Forward to TestClient, then lose or corrupt one committed create response."""

    def __init__(self, client, *, fault_path=None, missing_id_path=None):
        self.client = client
        self.fault_path = fault_path
        self.missing_id_path = missing_id_path
        self.triggered = False
        self.committed_id = None
        self.events = []

    def request(self, method, path, *, headers, json):
        self.events.append((method, path))
        response = self.client.request(method, path, headers=headers, json=json)
        if self.triggered or method != "POST":
            return response
        if path == self.fault_path:
            self.triggered = True
            payload = response.json()
            self.committed_id = payload.get("id") if isinstance(payload, dict) else None
            raise TimeoutError("response lost after committed create")
        if path == self.missing_id_path:
            self.triggered = True
            payload = response.json()
            self.committed_id = payload.get("id") if isinstance(payload, dict) else None
            return _StubResponse(response.status_code, {"name": "id omitted"})
        return response


def _silence_run_matrices(verifier, monkeypatch):
    """Keep run-level teardown tests focused on setup/reconciliation ordering."""
    for method_name in (
        "anon_sweep",
        "pedr_anon_sweep",
        "pedr1b_anon_sweep",
        "pedr1c_anon_sweep",
        "seeded_matrix",
        "list_isolation_check",
        "pedr_scope_matrix",
        "pedr1b_scope_matrix",
        "pedr1c_scope_matrix",
        "service_log_write_matrix",
    ):
        monkeypatch.setattr(
            verifier,
            method_name,
            lambda *args, **kwargs: None,
        )


def test_run_reconciles_api_key_when_committed_response_is_lost(
    client,
    db_session,
    owner_principal,
    monkeypatch,
):
    """The API-key finally covers a commit followed by transport failure."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    transport = _ForwardingFaultTransport(
        client,
        fault_path=f"{settings.api_v1_prefix}/auth/api-keys",
    )
    verifier = RbacVerifier(transport, log=lambda _message: None)

    with pytest.raises(HarnessError, match="api-key mint raised TimeoutError"):
        verifier.run(OWNER_EMAIL, OWNER_PW)

    assert transport.committed_id is not None
    db_session.expire_all()
    assert (
        db_session.query(APIKey)
        .filter(APIKey.name.like(f"{verifier._run_tag}%"))
        .count()
        == 0
    )
    assert verifier.teardown_failures == []


def test_run_reconciles_user_when_committed_response_is_lost(
    client,
    db_session,
    owner_principal,
    monkeypatch,
):
    """A response-lost throwaway user is found by its unique email prefix."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    transport = _ForwardingFaultTransport(
        client,
        fault_path=f"{settings.api_v1_prefix}/admin/users",
    )
    verifier = RbacVerifier(transport, log=lambda _message: None)
    _silence_run_matrices(verifier, monkeypatch)

    with pytest.raises(HarnessError, match="member provisioning raised TimeoutError"):
        verifier.run(OWNER_EMAIL, OWNER_PW)

    assert transport.committed_id is not None
    db_session.expire_all()
    assert (
        db_session.query(User)
        .filter(User.email.like(f"{verifier._run_tag}-%"))
        .count()
        == 0
    )
    assert (
        db_session.query(APIKey)
        .filter(APIKey.name.like(f"{verifier._run_tag}%"))
        .count()
        == 0
    )
    assert verifier.teardown_failures == []


def test_run_reconciles_missing_id_artifact_before_user_purge(
    client,
    db_session,
    owner_principal,
    monkeypatch,
):
    """A missing collection id is reconciled before user FKs can become NULL."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    owner_space = Workspace(name=f"run-order-{uuid4().hex[:8]}")
    db_session.add(owner_space)
    db_session.flush()
    existing_project = Project(
        name=f"Run-order existing project {uuid4().hex[:8]}",
        owner_id=owner_principal.id,
        workspace_id=owner_space.id,
    )
    db_session.add(existing_project)
    db_session.commit()
    project_id = existing_project.id

    transport = _ForwardingFaultTransport(
        client,
        missing_id_path=f"{settings.api_v1_prefix}/collections",
    )
    verifier = RbacVerifier(transport, log=lambda _message: None)
    _silence_run_matrices(verifier, monkeypatch)
    real_login = verifier.login

    def _budget_free_local_login(email, password):
        if email == OWNER_EMAIL:
            return real_login(email, password)
        return "unused-local-principal-token"

    monkeypatch.setattr(verifier, "login", _budget_free_local_login)

    code = verifier.run(OWNER_EMAIL, OWNER_PW)

    assert code == 1
    assert transport.committed_id is not None
    collection_delete_index = transport.events.index(
        (
            "DELETE",
            f"{settings.api_v1_prefix}/collections/{transport.committed_id}",
        )
    )
    first_user_delete_index = next(
        index
        for index, (method, path) in enumerate(transport.events)
        if method == "DELETE" and f"{settings.api_v1_prefix}/admin/users/" in path
    )
    assert collection_delete_index < first_user_delete_index

    db_session.expire_all()
    assert (
        db_session.query(Collection)
        .filter(Collection.name.like(f"{verifier._run_tag}%"))
        .count()
        == 0
    )
    assert (
        db_session.query(Mission)
        .filter(Mission.title.like(f"{verifier._run_tag}%"))
        .count()
        == 0
    )
    assert (
        db_session.query(User)
        .filter(User.email.like(f"{verifier._run_tag}-%"))
        .count()
        == 0
    )
    assert (
        db_session.query(APIKey)
        .filter(APIKey.name.like(f"{verifier._run_tag}%"))
        .count()
        == 0
    )
    reused_project = db_session.get(Project, project_id)
    assert reused_project is not None
    assert reused_project.deleted_at is None
    assert verifier.teardown_failures == []


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


class _Pedr1cTransport:
    """Stateful alternate-path transport that can model safe or leaky behavior."""

    project_id = str(uuid4())
    chunk_id = str(uuid4())
    foreign_space_id = str(uuid4())
    accessible_project_id = str(uuid4())
    accessible_space_id = str(uuid4())
    owner_history_id = str(uuid4())
    newer_viewer_history_id = str(uuid4())
    foreign_preview = "foreign preview known only to the fixture owner"

    def __init__(self, *, leaky: bool, content_leak: str | None = None):
        self.leaky = leaky
        self.content_leak = content_leak
        self.role_saved: dict[str, str] = {}
        self.role_history: dict[str, str] = {}
        self.owner_saved_ids = {
            "member": str(uuid4()),
            "viewer": str(uuid4()),
        }
        self.role_collection: dict[str, str] = {}
        self.foreign_collection_id: str | None = None
        self.collection_notes: dict[str, str] = {}
        self.report_payloads: dict[str, dict] = {}
        self.deleted_reports: set[str] = set()
        self.deleted_collections: set[str] = set()
        self.memberships: set[tuple[str, str]] = set()
        self.revoked_memberships: set[tuple[str, str]] = set()
        self.cross_saved_probes: set[tuple[str, str]] = set()
        self.cross_saved_probe_ids: dict[str, set[str]] = {
            "member": set(),
            "viewer": set(),
        }
        self.cross_history_probe_ids: dict[str, set[str]] = {
            "member": set(),
            "viewer": set(),
        }

    @staticmethod
    def _token(headers):
        return headers.get("Authorization", "").removeprefix("Bearer ")

    def _empty_execution(self, *, history_id=None):
        payload = {
            "rag": {
                "answer": _RAG_EMPTY_ANSWER,
                "sources": [],
                "citations": [],
            },
            "semantic": {"results": []},
        }
        if history_id is not None:
            payload["entry"] = {
                "id": history_id,
                "result_count": 0,
                "top_chunks": [],
            }
        return payload

    def _leaky_execution(self, *, history_id=None):
        payload = {
            "rag": {
                "answer": "foreign answer",
                "sources": [{"chunk_id": self.chunk_id}],
                "citations": [{"chunk_id": self.chunk_id}],
            },
            "semantic": {"results": [{"chunk_id": self.chunk_id}]},
        }
        if history_id is not None:
            payload["entry"] = {
                "id": history_id,
                "result_count": 1,
                "top_chunks": [self.chunk_id],
            }
        return payload

    def _content_only_execution(self, *, history_id=None):
        payload = self._empty_execution(history_id=history_id)
        payload["rag"]["answer"] = "foreign answer with otherwise-empty metadata"
        return payload

    def _create_report(
        self,
        *,
        collection_id: str | None = None,
        leaky: bool | None = None,
    ) -> _StubResponse:
        report_id = str(uuid4())
        leaks = self.leaky if leaky is None else leaky
        sources = (
            [{"source_type": "chunk", "source_id": self.chunk_id}]
            if leaks
            else (
                [{"source_type": "collection", "source_id": collection_id}]
                if collection_id is not None
                else []
            )
        )
        self.report_payloads[report_id] = {
            "content": "foreign report" if leaks else _SYNTHESIS_EMPTY_CONTENT,
            "citations": [{"chunk_id": self.chunk_id}] if leaks else [],
            "chunk_count": 1 if leaks else 0,
            "sources": sources,
        }
        payload = self.report_payloads[report_id]
        return _StubResponse(
            201,
            {
                "id": report_id,
                "content": payload["content"],
                "citations": payload["citations"],
            },
        )

    def request(self, method, path, *, headers, json):
        token = self._token(headers)
        role = token.removesuffix("-jwt")

        if method == "GET" and path.endswith(f"/projects/{self.project_id}"):
            return _StubResponse(
                200,
                {"id": self.project_id, "workspace_id": self.foreign_space_id},
            )

        if method == "GET" and "/projects?page_size=100" in path:
            if token == _SECOND_OWNER_TOKEN:
                rows = [
                    {
                        "id": self.project_id,
                        "workspace_id": self.foreign_space_id,
                    },
                    {
                        "id": self.accessible_project_id,
                        "workspace_id": self.accessible_space_id,
                    },
                ]
            else:
                rows = [
                    {
                        "id": self.accessible_project_id,
                        "workspace_id": self.accessible_space_id,
                    }
                ]
            return _StubResponse(200, {"data": rows})

        if method == "POST" and "/admin/spaces/" in path and path.endswith(
            "/members"
        ):
            self.memberships.add((path, str(json["user_id"])))
            return _StubResponse(201, {"user_id": json["user_id"]})

        if method == "DELETE" and "/admin/spaces/" in path and "/members/" in path:
            user_id = path.rsplit("/", 1)[-1]
            self.revoked_memberships.add((path, user_id))
            return _StubResponse(200, {"status": "removed"})

        if method == "POST" and path.endswith("/saved-searches"):
            if token == _SECOND_OWNER_TOKEN:
                deny_role = next(
                    candidate
                    for candidate in ("member", "viewer")
                    if f"foreign for {candidate}" in str(json.get("name"))
                )
                saved_id = self.owner_saved_ids[deny_role]
            else:
                saved_id = self.role_saved.setdefault(role, str(uuid4()))
                self.role_history.setdefault(role, str(uuid4()))
            return _StubResponse(201, {"id": saved_id})

        if method == "GET" and path.endswith("/saved-searches"):
            ids = [self.role_saved[role]]
            if self.leaky:
                ids.extend(self.owner_saved_ids.values())
            return _StubResponse(200, {"items": [{"id": item} for item in ids]})

        if method in {"PUT", "DELETE"} and "/saved-searches/" in path:
            saved_id = path.rsplit("/", 1)[-1]
            if saved_id in self.owner_saved_ids.values() and token != _SECOND_OWNER_TOKEN:
                self.cross_saved_probes.add((role, method))
                self.cross_saved_probe_ids[role].add(saved_id)
                return _StubResponse(204 if self.leaky else 404, {})
            return _StubResponse(204 if method == "DELETE" else 200, {})

        if method == "POST" and "/saved-searches/" in path and path.endswith(
            "/execute"
        ):
            saved_id = path.rsplit("/", 2)[-2]
            if saved_id in self.owner_saved_ids.values() and token != _SECOND_OWNER_TOKEN:
                if self.leaky:
                    return _StubResponse(200, self._leaky_execution())
                return _StubResponse(404, {})
            payload = (
                self._leaky_execution()
                if self.leaky
                else (
                    self._content_only_execution()
                    if self.content_leak == "rag"
                    else self._empty_execution()
                )
            )
            return _StubResponse(200, payload)

        if method == "GET" and "/search/history" in path:
            owner_entry = {
                "id": self.owner_history_id,
                "query_text": _PEDR_SCOPE_QUERY,
                "filters": {"project_id": self.project_id},
                "result_count": 1,
                "top_chunks": [self.chunk_id],
                "owner_id": _SECOND_OWNER_ID,
                "metadata": {},
            }
            if token == _SECOND_OWNER_TOKEN:
                newer_viewer_entry = {
                    "id": self.newer_viewer_history_id,
                    "query_text": _PEDR_SCOPE_QUERY,
                    "filters": {"project_id": self.project_id},
                    "result_count": 0,
                    "top_chunks": [],
                    "owner_id": _VIEWER_ID,
                    "metadata": {},
                }
                return _StubResponse(
                    200,
                    {"entries": [newer_viewer_entry, owner_entry]},
                )
            own_entry = {
                "id": self.role_history[role],
                "query_text": _PEDR_SCOPE_QUERY,
                "filters": {"project_id": self.project_id},
                "result_count": 1 if self.leaky else 0,
                "top_chunks": [self.chunk_id] if self.leaky else [],
                "owner_id": _MEMBER_ID if role == "member" else _VIEWER_ID,
                "metadata": {"saved_search_id": self.role_saved[role]},
            }
            entries = [own_entry, owner_entry] if self.leaky else [own_entry]
            return _StubResponse(200, {"entries": entries})

        if method == "POST" and "/search/replay/" in path:
            history_id = path.rsplit("/", 1)[-1]
            if history_id in {
                self.owner_history_id,
                self.newer_viewer_history_id,
            }:
                self.cross_history_probe_ids[role].add(history_id)
            if history_id == self.newer_viewer_history_id:
                if role == "viewer":
                    return _StubResponse(
                        200,
                        self._empty_execution(history_id=history_id),
                    )
                return _StubResponse(404, {})
            if history_id == self.owner_history_id:
                if self.leaky:
                    return _StubResponse(
                        200,
                        self._leaky_execution(history_id=history_id),
                    )
                return _StubResponse(404, {})
            payload = (
                self._leaky_execution(history_id=history_id)
                if self.leaky
                else (
                    self._content_only_execution(history_id=history_id)
                    if self.content_leak == "replay"
                    else self._empty_execution(history_id=history_id)
                )
            )
            return _StubResponse(200, payload)

        if method == "POST" and path.endswith("/collections"):
            if token == _SECOND_OWNER_TOKEN:
                if self.foreign_collection_id is None:
                    self.foreign_collection_id = str(uuid4())
                collection_id = self.foreign_collection_id
            else:
                collection_id = self.role_collection.setdefault(role, str(uuid4()))
            return _StubResponse(201, {"id": collection_id})

        if method == "POST" and path.endswith("/chunks"):
            collection_id = path.rsplit("/", 2)[-2]
            if token == _SECOND_OWNER_TOKEN or self.leaky:
                note = str((json or {}).get("notes") or "")
                self.collection_notes[collection_id] = note
                return _StubResponse(
                    201,
                    {
                        "chunk_id": self.chunk_id,
                        "chunk_content": self.foreign_preview,
                    },
                )
            return _StubResponse(403, {})

        if method == "GET" and path.endswith("/collections"):
            return _StubResponse(
                200,
                {
                    "data": [
                        {
                            "id": self.role_collection[role],
                            "item_count": 1 if self.leaky else 0,
                        }
                    ]
                },
            )

        if method == "GET" and path.endswith("/export"):
            collection_id = path.rsplit("/", 2)[-2]
            if self.leaky:
                text = (
                    "**Total Chunks:** 1\n"
                    f"{self.collection_notes.get(collection_id, '')}\n"
                    f"{self.foreign_preview}"
                )
            elif self.content_leak == "export":
                text = (
                    "**Total Chunks:** 0\n"
                    f"{self.collection_notes.get(collection_id, '')}\n"
                    f"{self.foreign_preview}"
                )
            else:
                text = "**Total Chunks:** 0"
            return _StubResponse(200, {}, text=text)

        if method == "GET" and "/collections/" in path:
            items = (
                [{"chunk_id": self.chunk_id, "chunk_content": "foreign"}]
                if self.leaky
                else []
            )
            return _StubResponse(
                200,
                {"item_count": len(items), "items": items},
            )

        if method == "DELETE" and "/chunks/" in path:
            return _StubResponse(204 if self.leaky else 404, {})

        if method == "DELETE" and "/collections/" in path:
            self.deleted_collections.add(path.rsplit("/", 1)[-1])
            return _StubResponse(204, {})

        if method == "POST" and path.endswith("/synthesize"):
            collection_id = str(json.get("collection_id"))
            if collection_id == self.foreign_collection_id:
                if not self.leaky:
                    return _StubResponse(403, {})
                return _StubResponse(
                    200,
                    {
                        "content": "foreign synthesis",
                        "citations": [{"chunk_id": self.chunk_id}],
                        "chunk_count": 1,
                    },
                )
            if json.get("project_id") is not None:
                if not self.leaky:
                    return _StubResponse(403, {})
                report = self._create_report(collection_id=collection_id)
                response = report.json()
                return _StubResponse(
                    200,
                    {
                        "content": response["content"],
                        "citations": response["citations"],
                        "chunk_count": 1,
                        "report_id": response["id"],
                    },
                )
            report = self._create_report(collection_id=collection_id)
            response = report.json()
            return _StubResponse(
                200,
                {
                    "content": response["content"],
                    "citations": response["citations"],
                    "chunk_count": 1 if self.leaky else 0,
                    "report_id": response["id"],
                },
            )

        if method == "POST" and path.endswith("/reports"):
            has_collection = json.get("collection_id") is not None
            has_chunks = json.get("chunk_ids") is not None
            if has_collection and has_chunks:
                if not self.leaky:
                    return _StubResponse(422, {})
                return self._create_report(collection_id=str(json["collection_id"]))
            if json.get("project_id") is not None:
                if not self.leaky:
                    return _StubResponse(403, {})
                return self._create_report(
                    collection_id=(str(json["collection_id"]) if has_collection else None)
                )
            if (
                has_collection
                and str(json["collection_id"]) == self.foreign_collection_id
            ):
                if not self.leaky:
                    return _StubResponse(403, {})
                return self._create_report(collection_id=str(json["collection_id"]))
            return self._create_report(
                collection_id=(str(json["collection_id"]) if has_collection else None)
            )

        if method == "GET" and "/reports/" in path:
            report_id = path.rsplit("/", 1)[-1]
            payload = dict(self.report_payloads[report_id])
            if self.content_leak == "report":
                payload["content"] = "foreign report with safe metadata"
            return _StubResponse(200, payload)

        if method == "DELETE" and "/reports/" in path:
            self.deleted_reports.add(path.rsplit("/", 1)[-1])
            return _StubResponse(200, {"success": True})

        raise AssertionError(f"unexpected probe: {method} {path} {headers} {json}")


def _run_pedr1c_transport(*, leaky=False, content_leak=None):
    transport = _Pedr1cTransport(leaky=leaky, content_leak=content_leak)
    verifier = RbacVerifier(transport, log=lambda _message: None)
    verifier._pedr1b_fixture = (transport.project_id, transport.chunk_id)
    verifier._pedr1b_fixture_owner_role = "second_owner"
    verifier.pedr1c_scope_matrix(
        {
            "second_owner": _SECOND_OWNER_TOKEN,
            "member": "member-jwt",
            "viewer": "viewer-jwt",
        },
        {
            "second_owner": _SECOND_OWNER_ID,
            "member": _MEMBER_ID,
            "viewer": _VIEWER_ID,
        },
    )
    return verifier, transport


def test_run_tag_reconciliation_removes_response_lost_artifacts():
    """List reconciliation deletes committed creates even when no id was tracked."""

    class _ReconciliationTransport:
        def __init__(self, run_tag):
            self.artifacts = {
                "saved-searches": {
                    str(uuid4()): f"{run_tag} response-lost saved search",
                    str(uuid4()): "unrelated saved search",
                },
                "collections": {
                    str(uuid4()): f"{run_tag} response-lost collection",
                    str(uuid4()): "unrelated collection",
                },
                "reports": {
                    str(uuid4()): f"{run_tag} response-lost report",
                    str(uuid4()): "unrelated report",
                },
                "missions": {
                    str(uuid4()): f"{run_tag} response-lost mission",
                    str(uuid4()): "unrelated mission",
                },
            }

        def request(self, method, path, *, headers, json):
            del headers, json
            family = next(
                name for name in self.artifacts if f"/{name}" in path
            )
            values = self.artifacts[family]
            if method == "GET":
                label = "title" if family in {"reports", "missions"} else "name"
                rows = [
                    {"id": artifact_id, label: value}
                    for artifact_id, value in values.items()
                ]
                if family == "collections":
                    return _StubResponse(200, {"data": rows, "total": len(rows)})
                if family == "missions":
                    return _StubResponse(
                        200,
                        {
                            "data": rows,
                            "pagination": {
                                "page": 1,
                                "page_size": 100,
                                "total": len(rows),
                                "pages": 1,
                            },
                        },
                    )
                payload = {"items": rows}
                if family == "reports":
                    payload.update(
                        {"total": len(rows), "page": 1, "page_size": 100}
                    )
                else:
                    payload["limit_per_user"] = 50
                return _StubResponse(200, payload)
            artifact_id = path.split("?", 1)[0].rsplit("/", 1)[-1]
            values.pop(artifact_id, None)
            return _StubResponse(204, {})

    run_tag = f"rbac-verify-{uuid4().hex}"
    transport = _ReconciliationTransport(run_tag)
    verifier = RbacVerifier(transport, log=lambda _message: None)
    verifier._run_tag = run_tag

    verifier.reconcile_tagged_artifacts("owner-jwt")

    assert verifier.teardown_failures == []
    assert all(len(values) == 1 for values in transport.artifacts.values())
    assert all(
        not name.startswith(run_tag)
        for values in transport.artifacts.values()
        for name in values.values()
    )


def test_pedr1c_scope_matrix_accepts_exact_fail_closed_responses():
    """The alternate-path matrix stays green for exact empty/403/404 contracts."""
    verifier, transport = _run_pedr1c_transport()

    assert verifier.gaps == []
    assert verifier.teardown_failures == []
    assert len(transport.memberships) == 2
    assert len(transport.revoked_memberships) == 2
    assert transport.cross_saved_probes == {
        ("member", "PUT"),
        ("member", "DELETE"),
        ("viewer", "PUT"),
        ("viewer", "DELETE"),
    }
    assert len(transport.cross_saved_probe_ids["member"]) == 1
    assert len(transport.cross_saved_probe_ids["viewer"]) == 1
    assert (
        transport.cross_saved_probe_ids["member"]
        != transport.cross_saved_probe_ids["viewer"]
    )
    assert transport.report_payloads.keys() <= transport.deleted_reports
    assert set(transport.role_collection.values()) <= transport.deleted_collections
    assert transport.foreign_collection_id in transport.deleted_collections


def test_pedr1c_history_fixture_uses_exact_owner_id_before_cross_owner_replay():
    """A newer viewer row cannot masquerade as the privileged fixture owner's."""
    verifier, transport = _run_pedr1c_transport()

    assert verifier.gaps == []
    assert transport.cross_history_probe_ids == {
        "member": {transport.owner_history_id},
        "viewer": {transport.owner_history_id},
    }
    assert all(
        transport.newer_viewer_history_id not in history_ids
        for history_ids in transport.cross_history_probe_ids.values()
    )


def test_pedr1c_scope_matrix_flags_artifact_child_and_report_leaks():
    """Every alternate-path family must make the live harness go red when leaky."""
    verifier, transport = _run_pedr1c_transport(leaky=True)
    kinds = {gap.kind for gap in verifier.gaps}

    assert "SAVED-SEARCH-OWNER-LEAK" in kinds
    assert "SAVED-SEARCH-SCOPE-LEAK" in kinds
    assert "SEARCH-HISTORY-OWNER-LEAK" in kinds
    assert "SEARCH-REPLAY-SCOPE-LEAK" in kinds
    assert "COLLECTION-CHILD-READ-LEAK" in kinds
    assert "COLLECTION-CHILD-COUNT-LEAK" in kinds
    assert "COLLECTION-CHILD-EXPORT-LEAK" in kinds
    assert "REPORT-SOURCE-SCOPE-LEAK" in kinds
    assert "REPORT-SOURCE-PERSISTENCE-LEAK" in kinds
    assert "SYNTHESIS-REPORT-SCOPE-LEAK" in kinds
    assert "SYNTHESIS-REPORT-PERSISTENCE-LEAK" in kinds
    assert "REPORT-SOURCE-VALIDATION" in kinds
    assert "DENY-LEAK-2xx" in kinds
    deny_probes = {(gap.method, gap.path) for gap in verifier.gaps if gap.kind == "DENY-LEAK-2xx"}
    assert ("post", "/api/v1/synthesize") in deny_probes
    assert ("post", "/api/v1/reports") in deny_probes
    assert any(path.endswith("/chunks") for method, path in deny_probes if method == "post")
    assert any("/chunks/" in path for method, path in deny_probes if method == "delete")
    assert any(path.endswith("/execute") for method, path in deny_probes if method == "post")
    assert any("/saved-searches/" in path for method, path in deny_probes if method == "put")
    assert transport.report_payloads.keys() <= transport.deleted_reports
    assert verifier.report() == 1


@pytest.mark.parametrize(
    ("content_leak", "expected_kind"),
    [
        ("rag", "SAVED-SEARCH-SCOPE-LEAK"),
        ("replay", "SEARCH-REPLAY-SCOPE-LEAK"),
        ("report", "REPORT-SOURCE-PERSISTENCE-LEAK"),
        ("export", "COLLECTION-CHILD-EXPORT-LEAK"),
    ],
)
def test_pedr1c_content_only_leaks_make_the_harness_red(
    content_leak,
    expected_kind,
):
    """Content leaks fail even when every list, count, citation, and source is empty."""
    verifier, _transport = _run_pedr1c_transport(content_leak=content_leak)
    kinds = {gap.kind for gap in verifier.gaps}

    assert expected_kind in kinds
    assert "COLLECTION-CHILD-READ-LEAK" not in kinds
    assert "COLLECTION-CHILD-COUNT-LEAK" not in kinds
    if content_leak != "export":
        assert "COLLECTION-CHILD-EXPORT-LEAK" not in kinds
    assert verifier.report() == 1


def test_pedr1c_scope_matrix_fails_without_disposable_owner_fixture():
    """History cleanup must never fall back to the persistent bootstrap owner."""
    verifier = RbacVerifier(None, log=lambda _message: None)
    verifier._pedr1b_fixture = (str(uuid4()), str(uuid4()))
    verifier._pedr1b_fixture_owner_role = "owner"

    verifier.pedr1c_scope_matrix({"owner": "owner-jwt"})

    assert any(gap.kind == "NO-DISPOSABLE-OWNER" for gap in verifier.gaps)


def test_pedr1c_anon_sweep_can_detect_a_public_route():
    """The alternate-route anonymous sweep fails if even history is public."""

    class _Transport:
        def request(self, method, path, *, headers, json):
            status_code = 200 if path.endswith("/search/history") else 401
            return _StubResponse(status_code, {})

    verifier = RbacVerifier(_Transport(), log=lambda _message: None)

    verifier.pedr1c_anon_sweep()

    assert any(
        gap.kind == "anon-401" and gap.path.endswith("/search/history")
        for gap in verifier.gaps
    )


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("delete", "/api/v1/search/history", None),
        ("post", "/api/v1/collections", {"name": "anonymous collection"}),
        (
            "post",
            "/api/v1/saved-searches",
            {"name": "anonymous saved", "query_text": "must reject"},
        ),
        (
            "post",
            "/api/v1/reports",
            {"title": "anonymous report", "chunk_ids": [str(uuid4())]},
        ),
    ],
)
def test_pedr1c_mutating_routes_authenticate_before_valid_requests(
    client,
    method,
    path,
    body,
):
    """Destructive/create auth checks stay local so the live harness is harmless."""
    response = client.request(method, path, json=body)

    assert response.status_code == 401


def test_pedr1c_matrix_is_compatible_with_real_testclient_routes(
    client,
    db_session,
    monkeypatch,
):
    """The stateful matrix runs through FastAPI routes without touching providers."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    foreign_space = Workspace(name=f"foreign-{uuid4().hex[:8]}")
    accessible_space = Workspace(name=f"accessible-{uuid4().hex[:8]}")
    second_owner = User(
        email=f"pedr1c-owner-{uuid4().hex[:8]}@example.test",
        display_name="PEDR1C second owner",
        password_hash="not-a-real-hash",  # noqa: S106
        role=ROLE_OWNER,
    )
    member = User(
        email=f"pedr1c-member-{uuid4().hex[:8]}@example.test",
        display_name="PEDR1C member",
        password_hash="not-a-real-hash",  # noqa: S106
        role=ROLE_MEMBER,
    )
    viewer = User(
        email=f"pedr1c-viewer-{uuid4().hex[:8]}@example.test",
        display_name="PEDR1C viewer",
        password_hash="not-a-real-hash",  # noqa: S106
        role=ROLE_VIEWER,
    )
    db_session.add_all(
        [foreign_space, accessible_space, second_owner, member, viewer]
    )
    db_session.flush()
    foreign_project = Project(
        name="PEDR1C foreign fixture",
        owner_id=second_owner.id,
        workspace_id=foreign_space.id,
    )
    accessible_project = Project(
        name="PEDR1C allowed fixture",
        owner_id=second_owner.id,
        workspace_id=accessible_space.id,
    )
    db_session.add_all([foreign_project, accessible_project])
    db_session.flush()
    document = Document(
        project_id=foreign_project.id,
        name="PEDR1C foreign document",
        owner_id=second_owner.id,
        workspace_id=foreign_space.id,
    )
    db_session.add(document)
    db_session.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="PEDR1C foreign preview must never cross the scope boundary",
    )
    db_session.add(chunk)
    db_session.flush()
    db_session.add(
        SearchHistory(
            query_text=_PEDR_SCOPE_QUERY,
            search_mode="semantic",
            filters={"project_id": str(foreign_project.id)},
            result_count=1,
            top_k=1,
            owner_id=second_owner.id,
            user_label=second_owner.display_name,
            metadata_payload={},
            top_chunks=[str(chunk.id)],
        )
    )
    db_session.commit()
    # A prior run-level test can warm the process-global project metadata cache
    # before the per-test SQLite reset. Invalidate it after this fixture commit so
    # the live route matrix discovers these newly-created workspace scopes.
    get_cache_manager().invalidate_project_metadata()

    principals = {
        "second_owner": create_access_token(subject=str(second_owner.id)),
        "member": create_access_token(subject=str(member.id)),
        "viewer": create_access_token(subject=str(viewer.id)),
    }
    verifier = RbacVerifier(client, log=lambda _message: None)
    verifier._pedr1b_fixture = (str(foreign_project.id), str(chunk.id))
    verifier._pedr1b_fixture_owner_role = "second_owner"

    verifier.pedr1c_scope_matrix(
        principals,
        {
            "second_owner": str(second_owner.id),
            "member": str(member.id),
            "viewer": str(viewer.id),
        },
    )

    assert verifier.gaps == [], [str(gap) for gap in verifier.gaps]
    assert verifier.teardown_failures == []
    db_session.expire_all()
    assert (
        db_session.query(Collection)
        .filter(Collection.name.like(f"{verifier._run_tag}%"))
        .count()
        == 0
    )
    assert (
        db_session.query(Report)
        .filter(Report.title.like(f"{verifier._run_tag}%"))
        .count()
        == 0
    )
    assert (
        db_session.query(SavedSearch)
        .filter(SavedSearch.name.like(f"{verifier._run_tag}%"))
        .count()
        == 0
    )
    assert (
        db_session.query(SpaceMember)
        .filter(
            SpaceMember.workspace_id == accessible_space.id,
            SpaceMember.user_id.in_([member.id, viewer.id]),
        )
        .count()
        == 0
    )
