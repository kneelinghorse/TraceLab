# Sprint C — `rbac_enabled` Pre-Flip Checklist

**Status:** gates 1–6 GREEN. The flip itself (T46.6) is the only remaining step.
**Date:** 2026-05-31
**Scope:** evidence that activating deny-by-default (`rbac_enabled=true`) will close the
BOLA/IDOR surface without locking out the owner or existing users.

> ⚠️ Working tree is uncommitted (Derek commits at the boundary). All "Evidence" below
> refers to the current working tree, not yet committed.

## Gates (decision #245 / #260)

| # | Gate | Status | Evidence |
|---|------|--------|----------|
| 1 | `authorize()` wired into EVERY per-id read/write route, passing the request `db` session (fails closed) | ✅ | T46.2 + T46.5. `tests/test_rbac_route_enforcement_api.py` (60 tests: 401 on every per-id route; 403 non-owner/non-member; 200 owner/space-member; flag-off no-op). 6-agent fail-open audit: the 6 core routers clean. |
| 2 | `resource.owner_id == user.user_id` is UUID-vs-UUID on every auth path (a `str` owner_id false-denies) | ✅ | `tests/test_pre_flip_gates.py::TestGate2UuidEquality` (UUID==UUID allows; `str` owner_id denies — the teeth; resolved JWT/API-key principals + ORM column are `uuid.UUID`). Decision #263. |
| 3 | Granting `ROLE_OWNER` requires an OWNER principal (no admin→owner escalation) | ✅ | T46.4. `tests/test_owner_grant_policy.py` (admin→owner 403; owner→owner 200; admin→non-owner 200). |
| 4 | `is_active` enforced at login + per request; `is_last_owner` counts only ACTIVE owners | ✅ | T46.3. `tests/test_is_active_enforcement.py` (login 403; JWT + API-key stop on disable; last-active-owner disable/demote 409; lockout-impossible regression). |
| 5 | `owner_id` surfaced on `ProjectRead` | ✅ | T46.4. `app/schemas/project.py`; `test_owner_grant_policy.py::TestOwnerIdExposed`. |
| 6 | Owner-bootstrap idempotent + `AUTH_USERNAME` parity (migration-time ↔ runtime) | ✅ | Idempotency: `tests/test_ownership.py::TestEnsureOwnerBootstrap`. Parity: `tests/test_pre_flip_gates.py::TestGate6BootstrapParity` + **both** `app/services/ownership.bootstrap_owner_email` and Alembic **031** use `os.environ.get("AUTH_USERNAME", "tracelab-admin")` (verified line-for-line). |

## Deferred design questions (decision #260) — resolved

- **(a) Collection cross-project visibility** — collections have `workspace_id`/`owner_id`, no `project_id`; authorized by own-Space membership + owner. No project→space inheritance needed.
- **(b) Orphan `project_id=NULL` mission/report** — FAIL-CLOSED (owner+admin only), via the `_NO_PROJECT_FK` sentinel (T46.1, re-applied + verified; decisions #261/#263).
- **(c) MCP / webhook / runner service-role tier** — TRUSTED-ORIGIN CARVE-OUT (system origins bypass per-user `authorize()`); a formal service-role tier is deferred to a later sprint.

## Audit-surfaced routes (classified per the patterns above, T46.5)

| Route | Classification | Action |
|-------|----------------|--------|
| `GET /missions/{id}/related`, `GET /missions/{id}/quality` | per-id mission read | WIRED (T46.2) |
| `GET /missions/{id}/logs` | per-id mission read (human) | WIRED (T46.5) |
| `POST /missions/{id}/logs` | DeepSearch runner write (service-to-service) | CARVE-OUT — authn-only, documented in code (#260c) |
| `POST /jobs`, `GET /jobs/{id}` | `IngestionJob` has no owner_id → governed via parent Document | WIRED via Document (T46.5) |
| `GET /pedr/related/{urn}` | URN graph traversal = result-set scoping | DEFERRED — same bucket as the deferred list-endpoint row-filtering |

## Known NON-gating gap (not BOLA)

- **Login rate-limiting + failed-login audit logging** are not wired into `/login`
  (`app/core/rate_limit.py` exists but unused there). 4 pre-existing red tests in
  `tests/test_auth_hardening.py` (proven pre-existing via git-stash A/B). This is
  auth-hardening, independent of the authz flip; recommend a dedicated follow-up.

## T46.6 — the flip (NOT done here)

1. Bootstrap the owner FIRST (`ensure_owner_bootstrap` runs at startup; migration 031 already backfilled prod).
2. Set `rbac_enabled=true` (default and/or target deploy env per the rollout plan).
3. Full regression: owner never locked out, existing access preserved via Space membership, cross-user 403, orphan fail-closed, disabled-user blocked, MCP/webhook/runner unaffected.
4. Rollback: flipping back to `false` is a clean no-op (the policy short-circuits at the flag).

**Env parity requirement (gate 6):** the deploy environment MUST set the SAME
`AUTH_USERNAME` at migration time and runtime, or bootstrap/backfill resolve different
owner identities. Confirm on the target service before flipping.
