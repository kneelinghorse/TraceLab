#!/usr/bin/env python3
"""Live RBAC verification harness (Sprint 47 T47.2).

Runs the role × route matrix against a DEPLOYED TraceLab API and exits NON-ZERO on
any enforcement gap — the answer to "how do we know RBAC actually works in prod."

It provisions its OWN throwaway users (via the T47.1 admin API) and tears them down,
seeds its OWN resources and deletes them — no manual setup, no leaked cruft. It
needs only the bootstrap owner's login from the environment; nothing hand-crafted.

    AUTH_USERNAME=... AUTH_PASSWORD=... \
        python scripts/rbac_verify.py --base-url https://api.tracelab.aquex.ai

It PRECHECKS GET /admin/rbac-status first: if RBAC is OFF (or the endpoint is
missing) the matrix would falsely pass (everything 200), so a flag-off deploy fails
LOUD instead of silently green.

Checks:
  * anon -> 401 sweep across EVERY wired per-id route (PER_ID_ROUTES — kept in
    lockstep with tests/test_rbac_route_enforcement_api.py by the e2e_prod wrapper).
  * seeded authz matrix for project / collection / mission:
      - member -> 403 and viewer -> 403 on every per-id route of the seeded resource
        (the BOLA/IDOR deny requirement — a 200 here is a CRITICAL enforcement gap);
      - owner -> 2xx and second-owner -> 2xx on the canonical GET (an over-blocking
        guard: enforcement must not 403 the legitimate owner).
  * PEDR search-scope matrix:
      - anon -> 401 on PEDR search, related, preflight, and retrieval search;
      - member / viewer -> empty search responses for an inaccessible explicit
        project and a deny on that project's related-entity URN;
      - owner -> 2xx on the related-entity URN (over-blocking guard).
  * reports / documents / ingestion-jobs are anon-401-only in v1 (seeding a document
    needs a multipart upload; a report can trigger synthesis). They are reported
    LOUDLY as "not in the authz matrix" — no silent coverage gap — to be extended in
    T47.3.

The core (`RbacVerifier`) is transport-agnostic: it talks to any object exposing
``.request(method, url, headers=, json=)`` returning ``.status_code`` / ``.json()``
— an ``httpx.Client`` against prod, or a FastAPI ``TestClient`` for local
verification (see tests/integration/test_e2e_rbac_live.py).
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

DEFAULT_PREFIX = "/api/v1"
_PEDR_SCOPE_QUERY = "rbac verification tenant isolation"

# Throwaway-user password (>= 8 chars, per AdminUserCreate). Not a real secret — the
# users exist only for the duration of a run and are purged at the end.
_THROWAWAY_PASSWORD = "rbac-verify-throwaway-pw"  # noqa: S105 — ephemeral test-user password, not a secret


# --- the wired per-id routes (anon-401 sweep) ------------------------------------
# Mirrors tests/test_rbac_route_enforcement_api.py::PER_ID_ROUTES. The e2e_prod
# wrapper asserts this stays in lockstep with that list so the harness can never
# silently fall behind the routes that get wired.
def per_id_routes(prefix: str, rid: str) -> list[tuple[str, str]]:
    """(method, path) for every per-id route, with ``rid`` substituted for each id."""
    api = prefix
    return [
        ("get", f"{api}/projects/{rid}"),
        ("put", f"{api}/projects/{rid}"),
        ("delete", f"{api}/projects/{rid}?confirm=true"),
        ("get", f"{api}/projects/{rid}/stats"),
        ("post", f"{api}/projects/{rid}/restore"),
        ("patch", f"{api}/projects/{rid}"),
        ("get", f"{api}/collections/{rid}"),
        ("get", f"{api}/collections/{rid}/export"),
        ("put", f"{api}/collections/{rid}"),
        ("delete", f"{api}/collections/{rid}"),
        ("post", f"{api}/collections/{rid}/chunks"),
        ("delete", f"{api}/collections/{rid}/chunks/{rid}"),
        ("get", f"{api}/missions/{rid}"),
        ("patch", f"{api}/missions/{rid}"),
        ("delete", f"{api}/missions/{rid}"),
        ("get", f"{api}/missions/{rid}/export"),
        ("post", f"{api}/missions/{rid}/submit"),
        ("get", f"{api}/missions/{rid}/contract-preview"),
        ("post", f"{api}/missions/{rid}/promote-report"),
        ("get", f"{api}/reports/{rid}"),
        ("get", f"{api}/reports/{rid}/export"),
        ("put", f"{api}/reports/{rid}"),
        ("delete", f"{api}/reports/{rid}"),
        ("post", f"{api}/documents/{rid}/process"),
        ("get", f"{api}/documents/{rid}"),
        ("get", f"{api}/documents/{rid}/download"),
        ("get", f"{api}/documents/{rid}/chunks"),
        ("delete", f"{api}/documents/{rid}?confirm=true"),
        ("post", f"{api}/documents/{rid}/restore"),
        ("patch", f"{api}/documents/{rid}"),
        ("get", f"{api}/missions/{rid}/related"),
        ("get", f"{api}/missions/{rid}/quality"),
        ("get", f"{api}/missions/{rid}/logs"),
        ("post", f"{api}/jobs?document_id={rid}"),
        ("get", f"{api}/jobs/{rid}"),
    ]


def pedr_scope_routes(prefix: str, project_id: str) -> list[tuple[str, str, dict[str, Any] | None]]:
    """PEDR/retrieval routes whose tenant scope is verified outside PER_ID_ROUTES."""
    return [
        (
            "post",
            f"{prefix}/pedr/search",
            {
                "query": _PEDR_SCOPE_QUERY,
                "project_id": project_id,
                "top_k": 1,
                "enable_governance": False,
            },
        ),
        ("get", f"{prefix}/pedr/related/urn:research:project:{project_id}", None),
        ("post", f"{prefix}/pedr/preflight", {"query": _PEDR_SCOPE_QUERY}),
        (
            "post",
            f"{prefix}/retrieval/search",
            {"query": _PEDR_SCOPE_QUERY, "project_id": project_id, "top_k": 1},
        ),
    ]


# --- seedable resource specs (authz matrix) --------------------------------------
@dataclass
class SeedSpec:
    """How to seed one resource type over the API and which per-id routes to matrix."""

    name: str
    create_path: str
    make_body: Callable[[dict[str, Any]], dict[str, Any]]
    routes: list[tuple[str, str]]  # (method, path-template with {id}) per-id routes
    canonical_get: str  # path-template for the owner over-blocking guard
    delete_path: str  # path-template for teardown (owner DELETE)
    create_method: str = "post"
    delete_method: str = "delete"
    id_field: str = "id"


def _seed_specs(prefix: str) -> list[SeedSpec]:
    api = prefix
    run = uuid.uuid4().hex[:8]
    return [
        SeedSpec(
            name="project",
            create_path=f"{api}/projects",
            make_body=lambda ctx: {"name": f"rbac-verify-proj-{run}"},
            routes=[
                ("get", f"{api}/projects/{{id}}"),
                ("get", f"{api}/projects/{{id}}/stats"),
                ("put", f"{api}/projects/{{id}}"),
                ("patch", f"{api}/projects/{{id}}"),
                ("post", f"{api}/projects/{{id}}/restore"),
                ("delete", f"{api}/projects/{{id}}?confirm=true"),
            ],
            canonical_get=f"{api}/projects/{{id}}",
            delete_path=f"{api}/projects/{{id}}?confirm=true",
        ),
        SeedSpec(
            name="collection",
            create_path=f"{api}/collections",
            make_body=lambda ctx: {"name": f"rbac-verify-coll-{run}"},
            routes=[
                ("get", f"{api}/collections/{{id}}"),
                ("get", f"{api}/collections/{{id}}/export"),
                ("put", f"{api}/collections/{{id}}"),
                ("post", f"{api}/collections/{{id}}/chunks"),
                ("delete", f"{api}/collections/{{id}}"),
            ],
            canonical_get=f"{api}/collections/{{id}}",
            delete_path=f"{api}/collections/{{id}}",
        ),
        SeedSpec(
            name="mission",
            create_path=f"{api}/missions",
            make_body=lambda ctx: {
                "mission_id": f"RV{uuid.uuid4().hex[:8]}",
                "title": "rbac-verify mission",
                "objective": "verify rbac enforcement wiring on a real mission",
                "success_criteria": ["enforcement-check"],
                "project_id": ctx["project"],
            },
            routes=[
                ("get", f"{api}/missions/{{id}}"),
                ("get", f"{api}/missions/{{id}}/export"),
                ("get", f"{api}/missions/{{id}}/related"),
                ("get", f"{api}/missions/{{id}}/quality"),
                ("get", f"{api}/missions/{{id}}/logs"),
                ("get", f"{api}/missions/{{id}}/contract-preview"),
                ("patch", f"{api}/missions/{{id}}"),
                ("post", f"{api}/missions/{{id}}/submit"),
                ("post", f"{api}/missions/{{id}}/promote-report"),
                ("delete", f"{api}/missions/{{id}}"),
            ],
            canonical_get=f"{api}/missions/{{id}}",
            delete_path=f"{api}/missions/{{id}}",
        ),
    ]


# Per-id routes intentionally NOT in the seeded authz matrix in v1 — they get the
# anon-401 sweep only (seeding a document needs a multipart upload; a report can
# trigger synthesis; a job needs a document; the chunk sub-resource needs a real
# chunk). (method, path-template-with-{id}, no prefix). This is an EXPLICIT allowlist:
# check_coverage() asserts every wired per-id route is either seeded or listed here,
# so a newly-wired route can never silently fall into an untested gap (extend in T47.3).
_ANON_ONLY_ROUTES = [
    ("get", "/reports/{id}"),
    ("get", "/reports/{id}/export"),
    ("put", "/reports/{id}"),
    ("delete", "/reports/{id}"),
    ("post", "/documents/{id}/process"),
    ("get", "/documents/{id}"),
    ("get", "/documents/{id}/download"),
    ("get", "/documents/{id}/chunks"),
    ("delete", "/documents/{id}?confirm=true"),
    ("post", "/documents/{id}/restore"),
    ("patch", "/documents/{id}"),
    ("post", "/jobs?document_id={id}"),
    ("get", "/jobs/{id}"),
    ("delete", "/collections/{id}/chunks/{id}"),
]


@dataclass
class Gap:
    """One enforcement deviation (the harness exits non-zero if any exist)."""

    kind: str  # e.g. "anon-401", "member-403", "owner-200", "precheck"
    role: str
    method: str
    path: str
    expected: str
    actual: str

    def __str__(self) -> str:
        return (
            f"[{self.kind}] {self.role}: {self.method.upper()} {self.path} "
            f"-> expected {self.expected}, got {self.actual}"
        )


class HarnessError(RuntimeError):
    """A setup failure that makes the whole run meaningless (precheck/login)."""


class RbacVerifier:
    """Drives the role × route matrix against an injected HTTP transport."""

    def __init__(self, http: Any, *, prefix: str = DEFAULT_PREFIX, log: Callable[[str], None] | None = None):
        self._http = http
        self._prefix = prefix
        self._log = log or (lambda m: print(m, flush=True))
        self.gaps: list[Gap] = []
        self.notes: list[str] = []
        self.teardown_failures: list[str] = []  # leaked cruft -> non-zero exit

    # -- transport ----------------------------------------------------------------
    def _call(
        self, method: str, path: str, *, token: str | None = None, api_key: str | None = None, json: Any | None = None
    ) -> Any:
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if api_key:
            headers["X-API-Key"] = api_key
        return self._http.request(method.upper(), path, headers=headers, json=json)

    @staticmethod
    def _body_for(method: str) -> Any:
        # Mutating routes need a body to get PAST FastAPI body-parsing to the
        # in-handler authorize() (an absent body can 422 before authz runs). Update
        # schemas are all-optional, so {} is a valid no-op body that reaches authz.
        return {} if method in ("put", "patch", "post") else None

    # -- setup --------------------------------------------------------------------
    def login(self, email: str, password: str) -> str:
        resp = self._call("post", f"{self._prefix}/auth/login", json={"email": email, "password": password})
        if resp.status_code != 200:
            raise HarnessError(f"owner login failed: POST /auth/login -> {resp.status_code} {resp.text}")
        return resp.json()["access_token"]

    def mint_api_key(self, token: str) -> tuple[str, str]:
        """Mint an owner API key; return (plaintext_key, key_id). The id lets teardown
        delete the key so a run never leaks a key (and never hits the 10-key cap)."""
        resp = self._call("post", f"{self._prefix}/auth/api-keys", token=token, json={"name": "rbac-verify"})
        if resp.status_code != 201:
            raise HarnessError(f"owner api-key mint failed: POST /auth/api-keys -> {resp.status_code} {resp.text}")
        data = resp.json()
        return data["key"], data["id"]

    def precheck_rbac_status(self, owner_key: str) -> dict[str, Any]:
        resp = self._call("get", f"{self._prefix}/admin/rbac-status", api_key=owner_key)
        if resp.status_code != 200:
            raise HarnessError(
                f"rbac-status precheck failed: GET /admin/rbac-status -> "
                f"{resp.status_code} {resp.text} (endpoint missing or owner not admin?)"
            )
        body = resp.json()
        if not body.get("rbac_enabled"):
            raise HarnessError(
                "RBAC IS OFF on this deploy (rbac_enabled=false): the role×route "
                "matrix would FALSELY PASS (every route 200). Refusing to run. "
                f"rbac-status={body}"
            )
        self._log(
            f"rbac-status OK: enabled=True owner_count={body.get('owner_count')} "
            f"your_role={body.get('your_role')} policy_version={body.get('policy_version')}"
        )
        return body

    def create_throwaway_user(self, owner_key: str, role: str, run_id: str) -> tuple[str, str] | None:
        """Create a throwaway user at ``role``; return (user_id, email) or None if the
        owner principal may not mint that role (e.g. second-owner when not owner).

        Returns the id (NOT a logged-in session) so the CALLER registers it for
        teardown BEFORE attempting login — a login failure must never leak the user.
        """
        email = f"rbac-verify-{role}-{run_id}@tracelab-verify.invalid"
        resp = self._call(
            "post",
            f"{self._prefix}/admin/users",
            api_key=owner_key,
            json={
                "email": email,
                "password": _THROWAWAY_PASSWORD,
                "display_name": f"rbac-verify {role}",
                "role": role,
            },
        )
        if resp.status_code != 201:
            self.notes.append(
                f"could not provision {role}: POST /admin/users -> {resp.status_code} "
                f"{resp.text} — skipping that principal's checks"
            )
            return None
        return resp.json()["id"], email

    def seed(self, owner_key: str, spec: SeedSpec, ctx: dict[str, Any]) -> str | None:
        try:
            # make_body may read ctx for a dependency (mission needs ctx["project"]);
            # if a prior seed failed that key is absent -> skip gracefully, never crash
            # (a crash before report() is the worst failure: no result at all).
            body = spec.make_body(ctx)
        except KeyError as exc:
            self.notes.append(f"could not seed {spec.name}: missing dependency {exc} — skipping its authz matrix")
            return None
        resp = self._call(spec.create_method, spec.create_path, api_key=owner_key, json=body)
        # Accept 200 or 201: all create endpoints declare 201, but a project create
        # replayed via an Idempotency-Key returns its cached 201/200 — tolerate both.
        if resp.status_code not in (200, 201):
            self.notes.append(
                f"could not seed {spec.name}: {spec.create_method.upper()} "
                f"{spec.create_path} -> {resp.status_code} {resp.text} — "
                f"skipping its authz matrix"
            )
            return None
        return resp.json()[spec.id_field]

    def check_coverage(self) -> None:
        """Every wired per-id route must be either in the seeded authz matrix or the
        explicit _ANON_ONLY_ROUTES allowlist. An UNACCOUNTED route is a silent
        coverage gap (a new route wired without harness coverage) -> hard gap, so the
        harness can never report PASS while a route's authz is entirely untested."""
        marker = "RIDPLACEHOLDER"  # unique token so we can normalize ids back to {id}
        wired = {(m, p.replace(marker, "{id}")) for m, p in per_id_routes(self._prefix, marker)}
        seeded = {(m, t) for spec in _seed_specs(self._prefix) for m, t in spec.routes}
        acknowledged = {(m, f"{self._prefix}{p}") for m, p in _ANON_ONLY_ROUTES}
        for method, path in sorted(wired - seeded - acknowledged):
            self.gaps.append(Gap("UNACCOUNTED-ROUTE", "coverage", method, path, "seeded-or-anon-only", "neither"))

    # -- the matrix ---------------------------------------------------------------
    def _record(self, ok: bool, gap: Gap) -> None:
        if not ok:
            self.gaps.append(gap)

    def anon_sweep(self) -> None:
        """Every per-id route must reject an unauthenticated caller with 401."""
        rid = str(uuid.uuid4())
        for method, path in per_id_routes(self._prefix, rid):
            resp = self._call(method, path, json=self._body_for(method))
            self._record(
                resp.status_code == 401,
                Gap("anon-401", "anon", method, path, "401", str(resp.status_code)),
            )

    def pedr_anon_sweep(self) -> None:
        """All four PEDR/retrieval entry points reject anonymous callers."""
        project_id = str(uuid.uuid4())
        for method, path, body in pedr_scope_routes(self._prefix, project_id):
            resp = self._call(method, path, json=body)
            self._record(
                resp.status_code == 401,
                Gap("anon-401", "anon", method, path, "401", str(resp.status_code)),
            )

    @staticmethod
    def _search_rows(response: Any) -> list[dict[str, Any]] | None:
        """Return search rows, distinguishing an empty result from a bad shape."""
        try:
            payload = response.json()
        except Exception:  # pragma: no cover - real HTTP adapters vary
            return None
        rows = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return None
        if not all(isinstance(row, dict) for row in rows):
            return None
        return rows

    def _discover_pedr_search_project(self, owner_token: str | None) -> str | None:
        """Find an existing project that is known-positive on both search routes."""
        if not owner_token:
            return None

        retrieval_path = f"{self._prefix}/retrieval/search"
        discovery = self._call(
            "post",
            retrieval_path,
            token=owner_token,
            json={"query": _PEDR_SCOPE_QUERY, "top_k": 50},
        )
        if discovery.status_code != 200:
            self.notes.append(
                "pedr-search fixture discovery: owner POST /retrieval/search -> "
                f"{discovery.status_code}"
            )
            return None

        candidate_ids: list[str] = []
        discovery_rows = self._search_rows(discovery)
        if discovery_rows is None:
            self.notes.append(
                "pedr-search fixture discovery: owner retrieval returned invalid JSON shape"
            )
            return None
        for row in discovery_rows:
            try:
                candidate_id = str(uuid.UUID(str(row.get("project_id"))))
            except (TypeError, ValueError):
                continue
            if candidate_id not in candidate_ids:
                candidate_ids.append(candidate_id)

        for candidate_id in candidate_ids:
            routes = pedr_scope_routes(self._prefix, candidate_id)
            pedr_method, pedr_path, pedr_body = routes[0]
            retrieval_method, scoped_retrieval_path, retrieval_body = routes[3]
            retrieval = self._call(
                retrieval_method,
                scoped_retrieval_path,
                token=owner_token,
                json=retrieval_body,
            )
            if retrieval.status_code != 200 or not self._search_rows(retrieval):
                continue
            pedr = self._call(
                pedr_method,
                pedr_path,
                token=owner_token,
                json=pedr_body,
            )
            if pedr.status_code == 200 and self._search_rows(pedr):
                return candidate_id

        self.notes.append(
            "pedr-search fixture discovery: no project from the owner's top-50 "
            "retrieval results was positive on both explicit-project search routes"
        )
        return None

    def _note_owner_preflight_baseline(self, owner_token: str | None) -> None:
        """State transparently whether the preflight deny smoke is non-vacuous."""
        if not owner_token:
            self.notes.append(
                "pedr-preflight: no owner principal; scoped-empty checks are smoke only"
            )
            return
        response = self._call(
            "post",
            f"{self._prefix}/pedr/preflight",
            token=owner_token,
            json={"query": _PEDR_SCOPE_QUERY},
        )
        if response.status_code != 200:
            self.notes.append(
                "pedr-preflight: owner baseline returned "
                f"{response.status_code}; scoped-empty checks are smoke only"
            )
            return
        try:
            payload = response.json()
        except Exception:  # pragma: no cover - real HTTP adapters vary
            payload = {}
        if not isinstance(payload, dict) or not payload.get("match_count"):
            self.notes.append(
                "pedr-preflight: owner baseline had zero matches; member/viewer "
                "scoped-empty checks are smoke only, not a non-vacuous isolation proof"
            )

    def pedr_scope_matrix(self, project_id: str, principals: dict[str, str]) -> None:
        """Prove related denial and search isolation with a known-positive corpus."""
        routes = pedr_scope_routes(self._prefix, project_id)
        related_method, related_path, _ = routes[1]
        preflight_method, preflight_path, preflight_body = routes[2]

        for role in ("member", "viewer"):
            token = principals.get(role)
            if not token:
                continue

            related = self._call(related_method, related_path, token=token)
            if 200 <= related.status_code < 300:
                self.gaps.append(
                    Gap(
                        "DENY-LEAK-2xx",
                        role,
                        related_method,
                        related_path,
                        "403",
                        str(related.status_code),
                    )
                )
            elif related.status_code != 403:
                self.gaps.append(
                    Gap(
                        "PEDR-RELATED-STATUS",
                        role,
                        related_method,
                        related_path,
                        "403",
                        str(related.status_code),
                    )
                )

            preflight = self._call(
                preflight_method,
                preflight_path,
                token=token,
                json=preflight_body,
            )
            if preflight.status_code != 200:
                self.gaps.append(
                    Gap(
                        "PEDR-SCOPE-STATUS",
                        role,
                        preflight_method,
                        preflight_path,
                        "200",
                        str(preflight.status_code),
                    )
                )
                continue
            try:
                payload = preflight.json()
            except Exception:  # pragma: no cover - real HTTP adapters vary
                payload = {}
            scoped_empty = (
                isinstance(payload, dict)
                and payload.get("action") == "proceed"
                and payload.get("match_count") == 0
                and payload.get("matches") == []
            )
            actual = (
                f"action={payload.get('action')!r}, "
                f"match_count={payload.get('match_count')!r}, "
                f"matches={len(payload.get('matches') or [])}"
                if isinstance(payload, dict)
                else "non-object JSON"
            )
            self._record(
                scoped_empty,
                Gap(
                    "PEDR-SCOPE-LEAK",
                    role,
                    preflight_method,
                    preflight_path,
                    "empty scoped response",
                    actual,
                ),
            )

        for role in ("owner", "second_owner"):
            token = principals.get(role)
            if not token:
                continue
            resp = self._call(related_method, related_path, token=token)
            self._record(
                200 <= resp.status_code < 300,
                Gap(
                    "owner-overblock",
                    role,
                    related_method,
                    related_path,
                    "2xx",
                    str(resp.status_code),
                ),
            )

        owner_token = principals.get("owner")
        self._note_owner_preflight_baseline(owner_token)
        search_project_id = self._discover_pedr_search_project(owner_token)
        if search_project_id is None:
            self.gaps.append(
                Gap(
                    "NO-SEARCHABLE-PROJECT",
                    "setup",
                    "post",
                    f"{self._prefix}/retrieval/search",
                    "an owner-known-positive project on retrieval and PEDR search",
                    "none found",
                )
            )
            return

        search_routes = pedr_scope_routes(self._prefix, search_project_id)
        for role in ("member", "viewer"):
            token = principals.get(role)
            if not token:
                continue
            for method, path, body in (search_routes[0], search_routes[3]):
                response = self._call(method, path, token=token, json=body)
                if response.status_code != 200:
                    self.gaps.append(
                        Gap(
                            "PEDR-SCOPE-STATUS",
                            role,
                            method,
                            path,
                            "200",
                            str(response.status_code),
                        )
                    )
                    continue
                rows = self._search_rows(response)
                if rows is None:
                    self.gaps.append(
                        Gap(
                            "PEDR-SCOPE-SHAPE",
                            role,
                            method,
                            path,
                            "JSON object with a results list",
                            "invalid response shape",
                        )
                    )
                    continue
                self._record(
                    rows == [],
                    Gap(
                        "PEDR-SCOPE-LEAK",
                        role,
                        method,
                        path,
                        "zero rows for owner-known-positive project",
                        f"results={len(rows)}",
                    ),
                )

    def seeded_matrix(self, spec: SeedSpec, resource_id: str, principals: dict[str, str]) -> None:
        """member/viewer -> denied on every per-id route; owner/second-owner -> 2xx
        on the canonical GET (over-blocking guard).

        The HARD failure is precisely a non-owner receiving 2xx (the actual BOLA/IDOR
        leak — the mission's "200-where-403"). 403 is the clean, expected deny. Any
        other non-2xx (401/404/422/5xx) is ALSO a deny — no resource reached — but is
        recorded as a NOTE, not a failure: a mutating route can 422 on the empty body
        BEFORE its in-handler authorize() runs, and that is not an enforcement gap.
        """
        for role in ("member", "viewer"):
            token = principals.get(role)
            if not token:
                continue
            for method, tmpl in spec.routes:
                path = tmpl.format(id=resource_id)
                resp = self._call(method, path, token=token, json=self._body_for(method))
                sc = resp.status_code
                if 200 <= sc < 300:
                    self.gaps.append(Gap("DENY-LEAK-2xx", role, method, path, "403", str(sc)))
                elif sc != 403:
                    self.notes.append(f"{role} {method.upper()} {path} -> {sc} (denied, not via 403)")
        # Positive over-blocking guard: the legitimate owner is NOT denied on read.
        for role in ("owner", "second_owner"):
            token = principals.get(role)
            if not token:
                continue
            path = spec.canonical_get.format(id=resource_id)
            resp = self._call("get", path, token=token)
            self._record(
                200 <= resp.status_code < 300,
                Gap("owner-overblock", role, "get", path, "2xx", str(resp.status_code)),
            )

    def service_log_write_matrix(self, mission_id: str, principals: dict[str, str]) -> None:
        """The mission-log INGEST path (POST /missions/{id}/logs) is a service-to-
        service write gated to a SERVICE principal (T47.4), NOT per-user authorize().
        Prove the triad on a real seeded mission:

          * anon (no creds)        -> 401  (router-level authn still applies, flag-free)
          * a non-service human    -> 403  (a human-auth token can't spoof logs)  CRITICAL
          * the service principal  -> 2xx  (the legitimate runner is not over-blocked)

        A non-service human receiving 2xx here is the exact BOLA leak this mission
        closes, so it is reported as a DENY-LEAK-2xx (the harness's critical class).
        Owner/admin humans are INTENTIONALLY tested as denied too — the service gate
        is stricter than authorize(), which would allow them. A VALID log body is
        sent so the SERVICE GATE (not Pydantic body validation) decides the outcome;
        an empty body would 422 before the gate and prove nothing. The 2xx write is
        safe to leave: mission_logs FK is ON DELETE CASCADE, so mission teardown
        reaps it.
        """
        path = f"{self._prefix}/missions/{mission_id}/logs"
        body = {"logs": [{"level": "INFO", "message": "rbac-verify service-gate probe"}]}

        # anon -> 401 (authentication is router-level and independent of the flag)
        resp = self._call("post", path, json=body)
        self._record(
            resp.status_code == 401,
            Gap("anon-401", "anon", "post", path, "401", str(resp.status_code)),
        )

        # non-service humans (incl. owner) -> 403. A 2xx is the critical BOLA leak.
        human_checked = []
        for role in ("member", "viewer", "owner", "second_owner"):
            token = principals.get(role)
            if not token:
                continue
            human_checked.append(role)
            resp = self._call("post", path, token=token, json=body)
            sc = resp.status_code
            if 200 <= sc < 300:
                self.gaps.append(Gap("DENY-LEAK-2xx", role, "post", path, "403", str(sc)))
            elif sc != 403:
                self.notes.append(f"log-write: {role} POST {path} -> {sc} (denied, not via 403)")
        if not human_checked:
            # No human principal -> the deny half proves nothing. Loud, not silent.
            self.gaps.append(
                Gap("NO-DENY-PRINCIPAL", "service-gate", "post", path,
                    "a human principal to prove denial", "none provisioned")
            )

        # the service principal -> 2xx (over-blocking guard: the runner must still work)
        service_token = principals.get("service")
        if service_token:
            resp = self._call("post", path, token=service_token, json=body)
            self._record(
                200 <= resp.status_code < 300,
                Gap("service-overblock", "service", "post", path, "2xx", str(resp.status_code)),
            )
        else:
            # Mirror NO-DENY-PRINCIPAL: the service-ALLOW probe IS the over-block
            # guard that proves the legitimate runner is not denied — the go/no-go
            # signal for the rbac_enabled flip (a missing service account is exactly
            # the "log ingestion 403s at flip time" failure the rollout runbook
            # exists to prevent). This method is only reached against an rbac-ON
            # target (precheck aborts when OFF), so an un-provisionable service
            # principal must be a LOUD gap, never a silent green PASS.
            self.gaps.append(
                Gap(
                    "NO-SERVICE-PRINCIPAL", "service-gate", "post", path,
                    "a service principal to prove the runner is not over-blocked",
                    "none provisioned (could not mint role='service')",
                )
            )

    # -- teardown -----------------------------------------------------------------
    def delete_resource(self, owner_key: str, spec: SeedSpec, resource_id: str) -> None:
        path = spec.delete_path.format(id=resource_id)
        resp = self._call(spec.delete_method, path, api_key=owner_key)
        if not (200 <= resp.status_code < 300):
            self.teardown_failures.append(
                f"{spec.name} {resource_id}: {spec.delete_method.upper()} {path} -> {resp.status_code} {resp.text}"
            )

    def purge_user(self, owner_key: str, user_id: str) -> None:
        resp = self._call("delete", f"{self._prefix}/admin/users/{user_id}", api_key=owner_key)
        if not (200 <= resp.status_code < 300):
            self.teardown_failures.append(
                f"user {user_id}: DELETE /admin/users/{user_id} -> {resp.status_code} {resp.text}"
            )

    def delete_api_key(self, token: str, key_id: str) -> None:
        """Delete the owner's run key so a run never leaks a tl_ key (the owner is
        capped at 10). Authenticated with the owner JWT, not the key itself, so it
        works even as the very last teardown step."""
        resp = self._call("delete", f"{self._prefix}/auth/api-keys/{key_id}", token=token)
        if not (200 <= resp.status_code < 300):
            self.teardown_failures.append(
                f"owner api-key {key_id}: DELETE /auth/api-keys/{key_id} -> {resp.status_code} {resp.text}"
            )

    def list_isolation_check(self, owner_project_id: str, principals: dict[str, str]) -> None:
        """Spot-check list-endpoint row-filtering (T47.3): the owner's seeded project
        must NOT appear in a non-owner's GET /projects list. A present id is a
        cross-tenant LIST leak — the gap the per-id flip left open until T47.3."""
        path = f"{self._prefix}/projects?page_size=100"
        for role in ("member", "viewer"):
            token = principals.get(role)
            if not token:
                continue
            resp = self._call("get", path, token=token)
            if not (200 <= resp.status_code < 300):
                self.notes.append(f"list-check: {role} GET /projects -> {resp.status_code}")
                continue
            ids = {row.get("id") for row in resp.json().get("data", [])}
            if owner_project_id in ids:
                self.gaps.append(Gap("LIST-LEAK", role, "get", path, "owner's project absent", "present in list"))
        # Sanity: the owner DOES see their own project (guards over-filtering).
        owner_token = principals.get("owner")
        if owner_token:
            resp = self._call("get", path, token=owner_token)
            if 200 <= resp.status_code < 300:
                ids = {row.get("id") for row in resp.json().get("data", [])}
                if owner_project_id not in ids:
                    self.notes.append(
                        f"list-check: owner's project {owner_project_id} missing from their "
                        f"own /projects list (over-filtering or pagination?)"
                    )

    # -- orchestration ------------------------------------------------------------
    def run(self, owner_email: str, owner_password: str) -> int:
        """Run the full harness. Returns a process exit code (0 = all enforced)."""
        run_id = uuid.uuid4().hex[:8]
        owner_token = self.login(owner_email, owner_password)
        owner_key, owner_key_id = self.mint_api_key(owner_token)
        try:
            self.precheck_rbac_status(owner_key)

            self.check_coverage()  # every wired route must be seeded or anon-only

            self._log("anon-401 sweep across every per-id route...")
            self.anon_sweep()
            self._log("anon-401 sweep across PEDR/retrieval scope routes...")
            self.pedr_anon_sweep()

            provisioned: list[str] = []
            seeded: list[tuple[SeedSpec, str]] = []
            principals: dict[str, str] = {"owner": owner_token}
            try:
                for role in ("member", "viewer", "owner", "service"):
                    pname = "second_owner" if role == "owner" else role
                    created = self.create_throwaway_user(owner_key, role, run_id)
                    if not created:
                        continue
                    uid, email = created
                    provisioned.append(uid)  # track for teardown BEFORE login
                    try:
                        principals[pname] = self.login(email, _THROWAWAY_PASSWORD)
                    except HarnessError as exc:
                        self.notes.append(f"provisioned {role} ({uid}) but login failed: {exc}")
                self._log(f"provisioned principals: {sorted(p for p in principals if p != 'owner')}")
                # The seeded matrix's whole point is the member/viewer DENY check; if
                # neither could be provisioned it proves nothing -> loud gap, not a
                # silent green (a 409 from leftover cruft must not degrade to PASS).
                if "member" not in principals and "viewer" not in principals:
                    self.gaps.append(
                        Gap(
                            "NO-DENY-PRINCIPAL",
                            "setup",
                            "post",
                            f"{self._prefix}/admin/users",
                            "member or viewer provisioned",
                            "neither — deny matrix did not run",
                        )
                    )

                ctx: dict[str, Any] = {}
                for spec in _seed_specs(self._prefix):
                    rid = self.seed(owner_key, spec, ctx)
                    if rid is None:
                        continue
                    ctx[spec.name] = rid
                    seeded.append((spec, rid))
                    self._log(f"seeded {spec.name}={rid}; running authz matrix...")
                    self.seeded_matrix(spec, rid, principals)

                if "project" in ctx:
                    self.list_isolation_check(ctx["project"], principals)
                    self._log("PEDR/retrieval tenant-scope matrix...")
                    self.pedr_scope_matrix(ctx["project"], principals)

                if "mission" in ctx:
                    self._log("service-role log-ingest gate (POST .../logs)...")
                    self.service_log_write_matrix(ctx["mission"], principals)

                self.notes.append(
                    f"seeded authz matrix covers project/collection/mission; "
                    f"{len(_ANON_ONLY_ROUTES)} routes (reports/documents/jobs/chunk-subresource) "
                    f"are anon-401 sweep only — extend in T47.3"
                )
            finally:
                # Children before parents (mission references project); best-effort.
                for spec, rid in reversed(seeded):
                    self.delete_resource(owner_key, spec, rid)
                for uid in provisioned:
                    self.purge_user(owner_key, uid)
        finally:
            # Delete the run's owner key LAST (it invalidates owner_key) so the run
            # leaves zero cruft even if the matrix raised.
            self.delete_api_key(owner_token, owner_key_id)

        return self.report()

    def report(self) -> int:
        for note in self.notes:
            self._log(f"NOTE: {note}")
        leaks = [g for g in self.gaps if g.kind == "DENY-LEAK-2xx"]
        if leaks:
            self._log("\n*** CRITICAL: NON-OWNER RECEIVED 2xx WHERE DENY EXPECTED ***")
            for g in leaks:
                self._log(f"  {g}")
        other = [g for g in self.gaps if g.kind != "DENY-LEAK-2xx"]
        if other:
            self._log(f"\n{len(other)} other enforcement deviation(s):")
            for g in other:
                self._log(f"  {g}")
        # Leaked cruft is its own failure: the harness promised to leave nothing
        # behind. Surface it loudly and fail non-zero so an operator can clean up
        # (and so the owner doesn't silently march toward the 10-key cap).
        if self.teardown_failures:
            self._log(f"\n*** TEARDOWN INCOMPLETE — {len(self.teardown_failures)} item(s) need manual cleanup ***")
            for tf in self.teardown_failures:
                self._log(f"  {tf}")

        if self.gaps or self.teardown_failures:
            self._log(
                f"\nFAIL: {len(self.gaps)} enforcement gap(s), {len(self.teardown_failures)} teardown failure(s)."
            )
            return 1
        self._log(
            "\nPASS: anon-401 enforced on every per-id and PEDR/retrieval route + "
            "seeded authz matrix (project/collection/mission/PEDR scope) clean; "
            "no leaked cruft."
        )
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live RBAC verification harness (T47.2).")
    parser.add_argument("--base-url", required=True, help="Deployed API base URL, e.g. https://api.tracelab.aquex.ai")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="API prefix (default /api/v1)")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    owner_email = os.environ.get("AUTH_USERNAME")
    owner_password = os.environ.get("AUTH_PASSWORD")
    if not owner_email or not owner_password:
        print("AUTH_USERNAME and AUTH_PASSWORD must be set (the bootstrap owner login).", file=sys.stderr)
        return 2
    # AUTH_USERNAME may be a bare username (bootstrap derives <username>@tracelab.local).
    if "@" not in owner_email:
        owner_email = f"{owner_email}@tracelab.local"

    try:
        import httpx
    except ImportError:
        print("httpx is required to run against a live URL (pip install httpx).", file=sys.stderr)
        return 2

    with httpx.Client(base_url=args.base_url, timeout=args.timeout) as http:
        verifier = RbacVerifier(http, prefix=args.prefix)
        try:
            return verifier.run(owner_email, owner_password)
        except HarnessError as exc:
            print(f"\nHARNESS ABORTED (setup/precheck failure): {exc}", file=sys.stderr)
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
