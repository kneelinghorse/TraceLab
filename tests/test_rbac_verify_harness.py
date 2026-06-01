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
from scripts.rbac_verify import _THROWAWAY_PASSWORD, HarnessError, RbacVerifier, _seed_specs

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
