"""RBAC-3 mutation proof: the matrix must go RED on a real enforcement regression.

Sprint 55 RBAC-3, success criterion 4. A verifier that cannot fail is worth nothing,
and "it would have caught it" is not evidence. These tests introduce an ACTUAL code
regression into app/core/authorization.py — not a flag flip, which is the weaker
mutation the Sprint 47 tests already cover — and assert the harness reports a
DENY-LEAK-2xx and a non-zero exit. The control case proves the same code path is
clean when the regression is absent, so a green run means something.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import authorization
from app.core.config import settings
from app.core.security import ROLE_MEMBER, ROLE_OWNER
from app.main import app
from app.models.user import User
from scripts.rbac_verify import RbacVerifier, _seed_specs
from tests.test_rbac_verify_harness import (
    _TEST_PRINCIPAL_PW,
    OWNER_EMAIL,
    OWNER_PW,
    _create_principal,
)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def owner_principal(db_session):
    """Promote the seeded bootstrap user to OWNER.

    Mirrors the fixture in tests/test_rbac_verify_harness.py, which is module-local
    rather than in conftest. POST /admin/users with role=owner is owner-gated, so
    the harness cannot mint its second-owner principal without this.
    """
    user = db_session.query(User).filter(User.email == OWNER_EMAIL).first()
    assert user is not None, "conftest seed user missing"
    user.role = ROLE_OWNER
    db_session.commit()
    return user


def _drive_project_matrix(client, db_session, monkeypatch) -> RbacVerifier:
    """Run the seeded project authz matrix as a member against an owner's project.

    Sprint 56 RBAC-5: the member principal is seeded into the test database rather
    than minted by the harness, which no longer creates users at all. The mutation
    proof itself is unchanged — it still injects a real fail-open into authorize()
    and requires the matrix to catch it.
    """
    monkeypatch.setattr(settings, "rbac_enabled", True)
    verifier = RbacVerifier(client, log=lambda _m: None)
    owner_token = verifier.login(OWNER_EMAIL, OWNER_PW)
    owner_key, _ = verifier.mint_api_key(owner_token)
    _uid, member_email = _create_principal(db_session, ROLE_MEMBER, "mutation-proof")
    member_jwt = verifier.login(member_email, _TEST_PRINCIPAL_PW)
    spec = next(s for s in _seed_specs(settings.api_v1_prefix) if s.name == "project")
    rid = verifier.seed(owner_key, spec, {})
    assert rid is not None, "project seeding failed"
    verifier.seeded_matrix(spec, rid, {"member": member_jwt})
    return verifier


@pytest.mark.usefixtures("owner_principal")
def test_control_enforced_matrix_is_clean(client, db_session, monkeypatch):
    """CONTROL: with enforcement intact the same path produces no leak.

    Without this, the mutation test below could pass for the wrong reason (e.g. the
    matrix flagging everything regardless).
    """
    verifier = _drive_project_matrix(client, db_session, monkeypatch)
    leaks = [g for g in verifier.gaps if g.kind == "DENY-LEAK-2xx"]
    assert leaks == [], f"unexpected leak with enforcement intact: {leaks}"


@pytest.mark.usefixtures("owner_principal")
def test_mutant_fail_open_regression_is_caught(client, db_session, monkeypatch):
    """MUTANT: authorize() fails open for reads — the harness MUST catch it.

    This is the regression class that matters: not "someone turned RBAC off", which
    the precheck already catches loudly, but "someone edited the policy and a deny
    path quietly started returning True".
    """
    real_authorize = authorization.authorize

    def fail_open(user, action, resource, db=None):
        if action == "read":
            return True  # <-- the deliberate regression
        return real_authorize(user, action, resource, db)

    monkeypatch.setattr(authorization, "authorize", fail_open)
    # authorize_or_403 resolves the name at call time from this module, so the
    # patch reaches every route that gates on it.
    verifier = _drive_project_matrix(client, db_session, monkeypatch)

    leaks = [g for g in verifier.gaps if g.kind == "DENY-LEAK-2xx"]
    assert leaks, (
        "THE HARNESS DID NOT CATCH A FAIL-OPEN READ REGRESSION. A matrix that "
        "cannot go red is not verification."
    )
    assert verifier.report() != 0, "harness reported success despite a deny-leak"
