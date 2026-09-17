"""Baseline-relative performance budgets for the Sprint 52 aggregates (PERF-1).

Decision #458: every performance criterion is a baseline-relative or server-side
budget — a feature p95 minus a trivial-endpoint p95 measured from the SAME client
in the SAME run — never an absolute client-observed millisecond number, and the
receipt records the baseline next to the feature measurement. Learning #193 is the
why: an absolute number measured from a laptop over the public internet mostly
measures the laptop and the internet, so it either flakes or is set so loose it
can never fail. This repository already contains both failure modes —
tests/test_semantic_edge_e2e_validation.py asserts `avg < 5.0` ms of wall clock and
flakes under load, while tests/performance/test_concurrent_queries.py ends on
`assert service.count >= 100`, a count that would not notice a tenfold slowdown.

The baseline is GET /api/v1/auth/me: authenticated, one DB session, one
primary-key lookup, one small response. It travels the same middleware, auth,
session and serialization path as every aggregate below and then does O(1) work,
so subtracting it removes almost everything that is about this machine rather than
about the query. That is what makes the budgets portable between a laptop and a CI
runner.

These are GATES, not advice: this module runs in the backend-integration lane,
which is a required check (decision #421), so exceeding a budget blocks the merge.

WHAT THIS DOES NOT COVER, stated because a budget whose scope is unclear invites
being trusted for more than it measures. The authenticated principal in this
fixture set resolves to role ``admin`` (subject ``kneelinghorse``), and admin is
in ``_PRIVILEGED_ROLES``, so ``authorize()`` short-circuits and every aggregate
below runs its UNSCOPED query with no ownership filter. That is representative of
the operator who actually uses TraceLab — Derek is ``owner``, also privileged —
but it means the member-scoped variant of each query, which carries an extra
accessible-projects filter and could behave differently at volume, is NOT under
budget here. Covering it needs a non-privileged principal that authentication
will accept, and authentication resolves the JWT through its own
``SessionLocal()`` rather than the ``get_db`` override, so that is a fixture
change rather than a one-line edit. The two Sprint 52 surfaces with no budget at
all are the saved exception dashboards (UX-12) and the priority inbox (UX-13).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from jose import jwt

from app.core.config import settings
from app.core.security import _resolve_user_from_jwt
from app.models.mission import Mission
from app.models.project import Project
from app.models.user import User

pytestmark = pytest.mark.integration

_HASH = "placeholder-not-a-real-hash"  # noqa: S105 - fixture column value, never verified

#: Corpus size. A budget measured against an empty table is the vacuity this
#: project keeps finding elsewhere: every aggregate is fast over zero rows, so the
#: assertion could never fail and would not be evidence. The seeded volume is
#: asserted to actually reach the response before any timing is trusted.
SEEDED_MISSIONS = 200

#: Samples per endpoint per round. WARMUP calls are discarded: the first request
#: through a route pays one-off import, statement-compile and connection costs that
#: are not what a budget is about.
WARMUP = 5
SAMPLES = 40

#: Rounds per endpoint, of which the BEST (lowest) p95 is kept. Measured variance
#: is the reason: across four exploratory runs on a developer machine the Home
#: delta came out +23, +33, +34 and +157 ms, the last while the machine was busy.
#: Sizing a budget around that outlier would make it so loose it could not fail,
#: which is the vacuity this project keeps finding elsewhere. Contention only ever
#: ADDS time — it never makes a query faster — so the minimum across rounds is a
#: robust estimator of the real cost, and it is what makes a tight gate safe on a
#: shared CI runner.
ROUNDS = 3

#: Budgets as a p95 DELTA over the baseline, in milliseconds.
#:
#: Sized at roughly five times the worst delta observed across three
#: best-of-rounds runs on a developer machine (Home 22.8-28.4, activity_summary
#: 5.5-8.5, graph_stats 0.5-15.3, graph_neighborhood 12.3-28.4; the full table is
#: in the PERF-1 receipt). That multiplier is deliberate and is the honest tension
#: in this file: a CI runner is slower and noisier than a laptop, and a gate that
#: flakes is worse than no gate because it teaches people to re-run it. These are
#: FIRST budgets chosen to be reliable rather than tight, and they should be
#: tightened once a few CI runs have shown the real variance there.
#:
#: They are not vacuous even so. The regressions worth catching here are
#: order-of-magnitude, not percentage: an N+1 over the 200-mission corpus, or a
#: dropped index, moves these deltas by hundreds of milliseconds, not tens.
BUDGETS_MS = {
    "home": 150.0,
    "activity_summary": 75.0,
    "graph_stats": 75.0,
    "graph_neighborhood": 150.0,
}


def _p95(samples: list[float]) -> float:
    """95th percentile in milliseconds, nearest-rank so it is a real observation."""
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, round(0.95 * len(ordered)) - 1))
    return ordered[index] * 1000.0


def _measure(client, path: str, headers: dict[str, str]) -> tuple[float, int]:
    """Return (best_p95_ms, last_status) for `path`: min p95 over ROUNDS rounds."""
    for _ in range(WARMUP):
        client.get(path, headers=headers)
    round_p95s: list[float] = []
    status = 0
    for _ in range(ROUNDS):
        samples: list[float] = []
        for _ in range(SAMPLES):
            started = time.perf_counter()
            response = client.get(path, headers=headers)
            samples.append(time.perf_counter() - started)
            status = response.status_code
        round_p95s.append(_p95(samples))
    return min(round_p95s), status


@pytest.fixture
def perf_principal(client, db_session):
    """Mirror the authenticated principal into PG, then give it a real corpus.

    Authentication resolves the JWT through its OWN ``SessionLocal()``
    (app/core/security.py::_resolve_user_from_jwt), not through the ``get_db``
    override, so a user invented here is invisible to authn and a token minted
    here 401s. The principal therefore has to be the one the client already
    carries; what is missing is its row in the testcontainer, which is why
    GET /auth/me answers 404 rather than 200 in this fixture set. Recreating that
    row under the SAME id is what lets RBAC scope the aggregates to it.
    """
    token = client.headers["Authorization"].split(" ", 1)[1]
    subject = jwt.decode(
        token, settings.secret_key, algorithms=[settings.jwt_algorithm]
    )["sub"]
    # The subject is a legacy display_name, not a UUID, so resolve it exactly as
    # the app does rather than parsing it. _resolve_user_from_jwt reads the
    # SessionLocal database, which is where authn actually looks.
    principal = _resolve_user_from_jwt(subject)

    user = User(
        id=principal.user_id,
        email=principal.email or f"perf-{uuid4()}@example.test",
        display_name=principal.display_name or subject,
        password_hash=_HASH,
        role="member",
    )
    db_session.add(user)
    db_session.flush()

    project = Project(name=f"Perf budget project {uuid4().hex[:8]}", owner_id=user.id)
    db_session.add(project)
    db_session.flush()

    now = datetime.utcnow()
    db_session.add_all(
        [
            Mission(
                mission_id=uuid4().hex,
                project_id=project.id,
                title=f"Perf corpus mission {index}",
                objective="Give the aggregates something to aggregate",
                success_criteria=["Non-empty corpus"],
                status="completed",
                completed_at=now - timedelta(minutes=index),
                owner_id=user.id,
            )
            for index in range(SEEDED_MISSIONS)
        ]
    )
    db_session.commit()
    return user, project


def test_sprint_52_aggregates_stay_within_their_baseline_relative_budgets(
    client, perf_principal, monkeypatch
):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    _user, project = perf_principal
    # The client already carries the only credential authn will accept here.
    headers = dict(client.headers)
    api = settings.api_v1_prefix

    baseline_ms, baseline_status = _measure(client, f"{api}/auth/me", headers)
    assert baseline_status == 200, (
        f"baseline GET {api}/auth/me returned {baseline_status}; without a baseline "
        "every budget below would be an absolute number, which decision #458 forbids"
    )

    # The corpus must actually reach the aggregate. If Home reports fewer missions
    # than were seeded, the timings below describe a smaller query than the one
    # under budget, and a pass would prove nothing.
    home = client.get(f"{api}/home", headers=headers)
    assert home.status_code == 200, f"GET {api}/home -> {home.status_code} {home.text[:200]}"
    reported = home.json()["missions"]["total"]
    assert reported == SEEDED_MISSIONS, (
        f"Home reported {reported} missions but {SEEDED_MISSIONS} were seeded; the "
        "budget would be measured against the wrong corpus size"
    )

    targets = {
        "home": f"{api}/home",
        "activity_summary": f"{api}/activity/summary",
        "graph_stats": f"{api}/graph/stats",
        "graph_neighborhood": (
            f"{api}/graph/neighborhood?root_type=project&root_id={project.id}"
        ),
    }

    measured: dict[str, tuple[float, float, int]] = {}
    for name, path in targets.items():
        feature_ms, status = _measure(client, path, headers)
        measured[name] = (feature_ms, feature_ms - baseline_ms, status)

    # Report every measurement next to the baseline before asserting, so a failure
    # shows the whole picture and the receipt can quote it (decision #458).
    lines = [f"baseline GET {api}/auth/me p95 = {baseline_ms:.1f} ms"]
    for name, (feature_ms, delta_ms, status) in measured.items():
        lines.append(
            f"{name}: p95 {feature_ms:.1f} ms, delta {delta_ms:+.1f} ms "
            f"(budget {BUDGETS_MS[name]:.0f} ms), status {status}"
        )
    print("\n" + "\n".join(lines))  # noqa: T201 - the measurement IS the artifact

    for name, (_feature_ms, delta_ms, status) in measured.items():
        assert status == 200, f"{name} returned {status}; a non-200 was not timed as success"
        assert delta_ms < BUDGETS_MS[name], (
            f"{name} exceeded its baseline-relative budget: p95 delta "
            f"{delta_ms:.1f} ms over a {baseline_ms:.1f} ms baseline, budget "
            f"{BUDGETS_MS[name]:.0f} ms. This is a gate, not advice — investigate a "
            "new N+1 or a dropped index before raising the number."
        )
