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
  * RAG/synthesis/facet scope matrix:
      - anon -> 401 on all three PEDR-1B routes;
      - member / viewer -> no sources from an owner-positive RAG project, no
        citations from an owner-owned chunk, and facet projects limited to the
        caller's own project list.
  * alternate RAG/synthesis and collection-child matrix:
      - saved-search/history artifacts are owner-scoped and replay fail-closes;
      - foreign chunks cannot be added or removed through a caller-owned collection;
      - legacy mixed collections expose zero children/content/counts;
      - direct and collection-backed report creation persists zero foreign sources.
  * documents / ingestion-jobs remain anon-401-only (seeding a document needs a
    multipart upload). Reports and collection children also receive the non-vacuous
    PEDR-1C cross-tenant matrix above.

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
_RAG_EMPTY_ANSWER = "No accessible sources were found for this query."
_SYNTHESIS_EMPTY_CONTENT = (
    "No content available for synthesis. The collection or chunks are empty."
)

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


def pedr1b_scope_routes(
    prefix: str,
    project_id: str,
    chunk_id: str,
) -> list[tuple[str, str, dict[str, Any]]]:
    """RAG, synthesis, and facet routes scoped by PEDR-1B."""
    return [
        (
            "post",
            f"{prefix}/search",
            {
                "query": _PEDR_SCOPE_QUERY,
                "project_id": project_id,
                "top_k": 1,
                "search_mode": "semantic",
                "max_tokens": 64,
            },
        ),
        (
            "post",
            f"{prefix}/synthesize",
            {"chunk_ids": [chunk_id], "format": "summary"},
        ),
        ("post", f"{prefix}/facets", {"project_id": project_id}),
    ]


def pedr1c_anon_routes(
    prefix: str,
    resource_id: str,
) -> list[tuple[str, str, dict[str, Any] | None]]:
    """Alternate artifact routes that must reject anonymous callers."""
    return [
        ("get", f"{prefix}/collections", None),
        ("post", f"{prefix}/collections", {}),
        ("get", f"{prefix}/saved-searches", None),
        ("post", f"{prefix}/saved-searches", {}),
        ("put", f"{prefix}/saved-searches/{resource_id}", {}),
        ("delete", f"{prefix}/saved-searches/{resource_id}", None),
        ("post", f"{prefix}/saved-searches/{resource_id}/execute", None),
        ("get", f"{prefix}/search/history", None),
        ("post", f"{prefix}/search/replay/{resource_id}", None),
        ("get", f"{prefix}/reports", None),
        ("post", f"{prefix}/reports", {}),
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


def _seed_specs(prefix: str, *, run_tag: str | None = None) -> list[SeedSpec]:
    api = prefix
    tag = run_tag or f"rbac-verify-{uuid.uuid4().hex[:8]}"
    return [
        SeedSpec(
            name="project",
            create_path=f"{api}/projects",
            make_body=lambda ctx: {"name": f"{tag} seeded project"},
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
            make_body=lambda ctx: {"name": f"{tag} seeded collection"},
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
                "title": f"{tag} non-runnable mission",
                "objective": "verify rbac enforcement wiring on a real mission",
                "success_criteria": ["enforcement-check"],
                "project_id": ctx["project"],
                # A completed mission reaches authorize() first, then fails the
                # submit precondition with 400 if authorization ever fails open.
                # It can therefore never enter the DeepSearch queue during a live
                # verifier run, even when the very bug under test is present.
                "status": "completed",
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

# These routes remain in SeedSpec/check_coverage and are exercised by local
# TestClient tests, but are deliberately excluded from the deployed authenticated
# matrix because even the expected fail-open regression would mutate durable prod
# state. Anonymous 401 coverage remains live through per_id_routes().
_LOCAL_ONLY_AUTHZ_ROUTES = {
    ("project", "delete", "/projects/{id}?confirm=true"),
}


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
        self._pedr1b_fixture: tuple[str, str] | None = None
        self._pedr1b_fixture_owner_role: str | None = None
        self._principal_ids: dict[str, str] = {}
        self._run_tag = f"rbac-verify-{uuid.uuid4().hex}"

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
    def _body_for(method: str, path: str = "") -> Any:
        # Mutating routes need a body to get PAST FastAPI body-parsing to the
        # in-handler authorize() (an absent body can 422 before authz runs).
        if method == "post" and path.endswith("/chunks"):
            return {"chunk_id": str(uuid.uuid4())}
        # Update schemas are all-optional, and bodyless POST routes ignore an empty
        # JSON object, so this is a safe no-op body that reaches authorization.
        return {} if method in ("put", "patch", "post") else None

    def _tagged(self, label: str) -> str:
        """Return a unique, list-reconcilable name for a run-created artifact."""
        return f"{self._run_tag} {label}"

    # -- setup --------------------------------------------------------------------
    def login(self, email: str, password: str) -> str:
        resp = self._call("post", f"{self._prefix}/auth/login", json={"email": email, "password": password})
        if resp.status_code != 200:
            raise HarnessError(f"owner login failed: POST /auth/login -> {resp.status_code} {resp.text}")
        return resp.json()["access_token"]

    def mint_api_key(self, token: str) -> tuple[str, str]:
        """Mint an owner API key; return (plaintext_key, key_id). The id lets teardown
        delete the key so a run never leaks a key (and never hits the 10-key cap)."""
        try:
            resp = self._call(
                "post",
                f"{self._prefix}/auth/api-keys",
                token=token,
                json={"name": self._tagged("owner api key")},
            )
        except Exception as exc:
            raise HarnessError(
                f"owner api-key mint raised {type(exc).__name__}: {exc}"
            ) from exc
        if resp.status_code != 201:
            raise HarnessError(f"owner api-key mint failed: POST /auth/api-keys -> {resp.status_code} {resp.text}")
        data = resp.json()
        if not isinstance(data, dict) or not data.get("key") or not data.get("id"):
            raise HarnessError(
                "owner api-key mint returned 201 without key/id; reconciliation required"
            )
        return str(data["key"]), str(data["id"])

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
        email = f"{run_id}-{role}@tracelab-verify.invalid"
        try:
            resp = self._call(
                "post",
                f"{self._prefix}/admin/users",
                api_key=owner_key,
                json={
                    "email": email,
                    "password": _THROWAWAY_PASSWORD,
                    "display_name": self._tagged(f"{role} principal"),
                    "role": role,
                },
            )
        except Exception as exc:
            raise HarnessError(
                f"{role} provisioning raised {type(exc).__name__}: {exc}"
            ) from exc
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
            # a missing required dependency is a hard setup gap, never a soft skip.
            body = spec.make_body(ctx)
        except KeyError as exc:
            self.gaps.append(
                Gap(
                    "REQUIRED-SEED-FAILURE",
                    "setup",
                    spec.create_method,
                    spec.create_path,
                    f"{spec.name} seed with all dependencies",
                    f"missing dependency {exc}",
                )
            )
            return None
        try:
            resp = self._call(
                spec.create_method,
                spec.create_path,
                api_key=owner_key,
                json=body,
            )
        except Exception as exc:
            self.gaps.append(
                Gap(
                    "REQUIRED-SEED-FAILURE",
                    "setup",
                    spec.create_method,
                    spec.create_path,
                    f"2xx {spec.name} seed with id",
                    f"raised {type(exc).__name__}: {exc}",
                )
            )
            return None
        # Accept 200 or 201: all create endpoints declare 201, but a project create
        # replayed via an Idempotency-Key returns its cached 201/200 — tolerate both.
        if resp.status_code not in (200, 201):
            self.gaps.append(
                Gap(
                    "REQUIRED-SEED-FAILURE",
                    "setup",
                    spec.create_method,
                    spec.create_path,
                    f"2xx {spec.name} seed with id",
                    str(resp.status_code),
                )
            )
            return None
        payload = self._json_object(resp)
        resource_id = payload.get(spec.id_field) if payload is not None else None
        if not resource_id:
            self.gaps.append(
                Gap(
                    "REQUIRED-SEED-FAILURE",
                    "setup",
                    spec.create_method,
                    spec.create_path,
                    f"2xx {spec.name} seed with id",
                    "success response missing id",
                )
            )
            return None
        return str(resource_id)

    def discover_owned_project(self, owner_token: str) -> str:
        """Return a validated, non-deleted project owned by the bootstrap owner.

        The live verifier reuses this row and never creates/soft-deletes a project.
        If no exact owner match exists, mutation-free verification cannot proceed
        deterministically and the run aborts after its guaranteed cleanup.
        """
        me_path = f"{self._prefix}/auth/me"
        me = self._call("get", me_path, token=owner_token)
        me_payload = self._json_object(me)
        owner_id = me_payload.get("user_id") if me_payload is not None else None
        if me.status_code != 200 or not owner_id:
            raise HarnessError(
                f"safe project fixture failed: GET {me_path} -> {me.status_code} "
                "without owner user_id"
            )

        page = 1
        while True:
            list_path = f"{self._prefix}/projects?page={page}&page_size=100"
            listing = self._call("get", list_path, token=owner_token)
            payload = self._json_object(listing)
            rows = payload.get("data") if payload is not None else None
            pagination = payload.get("pagination") if payload is not None else None
            if listing.status_code != 200 or not isinstance(rows, list):
                raise HarnessError(
                    f"safe project fixture failed: GET {list_path} -> "
                    f"{listing.status_code} invalid list response"
                )
            for row in rows:
                if not isinstance(row, dict) or str(row.get("owner_id")) != str(owner_id):
                    continue
                project_id = row.get("id")
                detail_path = f"{self._prefix}/projects/{project_id}"
                detail = self._call("get", detail_path, token=owner_token)
                detail_payload = self._json_object(detail)
                if (
                    detail.status_code == 200
                    and detail_payload is not None
                    and str(detail_payload.get("id")) == str(project_id)
                    and str(detail_payload.get("owner_id")) == str(owner_id)
                ):
                    return str(project_id)
            pages = pagination.get("pages") if isinstance(pagination, dict) else None
            if not isinstance(pages, int):
                raise HarnessError(
                    f"safe project fixture failed: GET {list_path} missing pagination.pages"
                )
            if page >= pages:
                break
            page += 1
        raise HarnessError(
            "safe project fixture failed: no non-deleted project is owned by the "
            "bootstrap owner; refusing to create or soft-delete production state"
        )

    def check_coverage(self) -> None:
        """Every wired per-id route must be either in the seeded authz matrix or the
        explicit _ANON_ONLY_ROUTES allowlist. An UNACCOUNTED route is a silent
        coverage gap (a new route wired without harness coverage) -> hard gap, so the
        harness can never report PASS while a route's authz is entirely untested."""
        marker = "RIDPLACEHOLDER"  # unique token so we can normalize ids back to {id}
        wired = {(m, p.replace(marker, "{id}")) for m, p in per_id_routes(self._prefix, marker)}
        seeded = {(m, t) for spec in _seed_specs(self._prefix) for m, t in spec.routes}
        acknowledged = {(m, f"{self._prefix}{p}") for m, p in _ANON_ONLY_ROUTES}
        local_only = {
            (method, f"{self._prefix}{path}")
            for _name, method, path in _LOCAL_ONLY_AUTHZ_ROUTES
        }
        for method, path in sorted(local_only - seeded):
            self.gaps.append(
                Gap(
                    "LOCAL-ONLY-ROUTE-DRIFT",
                    "coverage",
                    method,
                    path,
                    "present in local seeded matrix",
                    "missing",
                )
            )
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
            resp = self._call(method, path, json=self._body_for(method, path))
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

    def pedr1b_anon_sweep(self) -> None:
        """All three RAG/synthesis/facet entry points reject anonymous callers."""
        project_id = str(uuid.uuid4())
        chunk_id = str(uuid.uuid4())
        for method, path, body in pedr1b_scope_routes(
            self._prefix,
            project_id,
            chunk_id,
        ):
            resp = self._call(method, path, json=body)
            self._record(
                resp.status_code == 401,
                Gap("anon-401", "anon", method, path, "401", str(resp.status_code)),
            )

    def pedr1c_anon_sweep(self) -> None:
        """Live-safe alternate routes reject anonymous callers without mutations."""
        resource_id = str(uuid.uuid4())
        for method, path, body in pedr1c_anon_routes(
            self._prefix,
            resource_id,
        ):
            response = self._call(method, path, json=body)
            self._record(
                response.status_code == 401,
                Gap(
                    "anon-401",
                    "anon",
                    method,
                    path,
                    "401",
                    str(response.status_code),
                ),
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

    @staticmethod
    def _rag_payload(response: Any) -> dict[str, Any] | None:
        """Return a RAG payload only when its source/citation lists are shaped."""
        try:
            payload = response.json()
        except Exception:  # pragma: no cover - real HTTP adapters vary
            return None
        if not isinstance(payload, dict):
            return None
        if not isinstance(payload.get("sources"), list):
            return None
        if not isinstance(payload.get("citations"), list):
            return None
        return payload

    @staticmethod
    def _facet_project_ids(response: Any) -> set[str] | None:
        """Extract UUID-shaped facet project values, rejecting malformed rows."""
        try:
            payload = response.json()
        except Exception:  # pragma: no cover - real HTTP adapters vary
            return None
        rows = payload.get("projects") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            return None
        project_ids: set[str] = set()
        for row in rows:
            try:
                project_ids.add(str(uuid.UUID(str(row.get("value")))))
            except (TypeError, ValueError):
                return None
        return project_ids

    @staticmethod
    def _synthesis_payload(response: Any) -> dict[str, Any] | None:
        """Return a synthesis payload only when its leak-sensitive fields are shaped."""
        try:
            payload = response.json()
        except Exception:  # pragma: no cover - real HTTP adapters vary
            return None
        if not isinstance(payload, dict):
            return None
        if not isinstance(payload.get("content"), str):
            return None
        if not isinstance(payload.get("citations"), list):
            return None
        if not isinstance(payload.get("chunk_count"), int):
            return None
        return payload

    @staticmethod
    def _facets_are_empty(response: Any) -> bool:
        """Require every facet aggregate to be empty, not only project labels."""
        try:
            payload = response.json()
        except Exception:  # pragma: no cover - real HTTP adapters vary
            return False
        if not isinstance(payload, dict):
            return False
        date_range = payload.get("date_range")
        return (
            payload.get("projects") == []
            and payload.get("document_types") == []
            and payload.get("source_types") == []
            and payload.get("tags") == []
            and isinstance(date_range, dict)
            and date_range.get("min") is None
            and date_range.get("max") is None
        )

    def _discover_pedr1b_fixture(
        self,
        owner_token: str | None,
    ) -> tuple[str, str] | None:
        """Find a real owner project/chunk proven positive on RAG and facets."""
        if not owner_token:
            return None

        retrieval = self._call(
            "post",
            f"{self._prefix}/retrieval/search",
            token=owner_token,
            json={"query": _PEDR_SCOPE_QUERY, "top_k": 50},
        )
        if retrieval.status_code != 200:
            self.notes.append(
                "pedr1b fixture discovery: owner retrieval returned "
                f"{retrieval.status_code}"
            )
            return None
        rows = self._search_rows(retrieval)
        if rows is None:
            self.notes.append(
                "pedr1b fixture discovery: owner retrieval returned invalid JSON shape"
            )
            return None

        candidates: list[tuple[str, str]] = []
        for row in rows:
            try:
                candidate = (
                    str(uuid.UUID(str(row.get("project_id")))),
                    str(uuid.UUID(str(row.get("chunk_id")))),
                )
            except (TypeError, ValueError):
                continue
            if candidate not in candidates:
                candidates.append(candidate)

        # RAG and synthesis are provider-backed, so bound fixture discovery instead
        # of turning a stale production corpus into dozens of paid probe calls.
        for project_id, chunk_id in candidates[:5]:
            rag_route, synthesis_route, facets_route = pedr1b_scope_routes(
                self._prefix,
                project_id,
                chunk_id,
            )
            facets = self._call(
                facets_route[0],
                facets_route[1],
                token=owner_token,
                json=facets_route[2],
            )
            facet_ids = (
                self._facet_project_ids(facets)
                if facets.status_code == 200
                else None
            )
            if facet_ids is None or project_id not in facet_ids:
                continue

            rag = self._call(
                rag_route[0],
                rag_route[1],
                token=owner_token,
                json=rag_route[2],
            )
            rag_payload = self._rag_payload(rag) if rag.status_code == 200 else None
            if not rag_payload or not rag_payload["sources"]:
                continue

            synthesis = self._call(
                synthesis_route[0],
                synthesis_route[1],
                token=owner_token,
                json=synthesis_route[2],
            )
            synthesis_payload = (
                self._synthesis_payload(synthesis)
                if synthesis.status_code == 200
                else None
            )
            if (
                synthesis_payload is None
                or synthesis_payload["chunk_count"] < 1
                or not synthesis_payload["content"].strip()
                or synthesis_payload["content"] == _SYNTHESIS_EMPTY_CONTENT
            ):
                continue
            return project_id, chunk_id

        self.notes.append(
            "pedr1b fixture discovery: none of the first five owner retrieval "
            "candidates was positive on explicit-project facets, RAG, and synthesis"
        )
        return None

    def pedr1b_scope_matrix(self, principals: dict[str, str]) -> None:
        """Prove RAG, synthesis, and facet isolation with owner-positive data."""
        # Prefer the disposable second owner. POST /search records history, and the
        # PEDR-1C owner_id FK lets user teardown cascade that probe artifact. The
        # bootstrap owner remains a compatibility fallback for focused harness tests.
        fixture_owner_role = (
            "second_owner" if principals.get("second_owner") else "owner"
        )
        fixture = self._discover_pedr1b_fixture(
            principals.get(fixture_owner_role)
        )
        if fixture is None:
            self.gaps.append(
                Gap(
                    "NO-PEDR1B-FIXTURE",
                    "setup",
                    "post",
                    f"{self._prefix}/retrieval/search",
                    "an owner-positive project/chunk on RAG and facets",
                    "none found",
                )
            )
            return

        project_id, chunk_id = fixture
        self._pedr1b_fixture = fixture
        self._pedr1b_fixture_owner_role = fixture_owner_role
        routes = pedr1b_scope_routes(self._prefix, project_id, chunk_id)
        for role in ("member", "viewer"):
            token = principals.get(role)
            if not token:
                continue

            list_path = f"{self._prefix}/projects?page_size=100"
            project_list = self._call("get", list_path, token=token)
            accessible_ids: set[str] | None = None
            if project_list.status_code == 200:
                try:
                    list_rows = project_list.json().get("data")
                except Exception:  # pragma: no cover - real HTTP adapters vary
                    list_rows = None
                if isinstance(list_rows, list) and all(
                    isinstance(row, dict) for row in list_rows
                ):
                    accessible_ids = {str(row.get("id")) for row in list_rows}
            if accessible_ids is None:
                self.gaps.append(
                    Gap(
                        "PEDR1B-PROJECT-LIST",
                        role,
                        "get",
                        list_path,
                        "200 with data list",
                        str(project_list.status_code),
                    )
                )

            rag_route, synthesis_route, facets_route = routes
            rag = self._call(
                rag_route[0],
                rag_route[1],
                token=token,
                json=rag_route[2],
            )
            if rag.status_code != 200:
                self.gaps.append(
                    Gap(
                        "PEDR1B-SCOPE-STATUS",
                        role,
                        rag_route[0],
                        rag_route[1],
                        "200",
                        str(rag.status_code),
                    )
                )
            else:
                payload = self._rag_payload(rag)
                self._record(
                    payload is not None
                    and payload.get("answer") == _RAG_EMPTY_ANSWER
                    and payload["sources"] == []
                    and payload["citations"] == [],
                    Gap(
                        "RAG-SCOPE-LEAK",
                        role,
                        rag_route[0],
                        rag_route[1],
                        "zero sources and citations",
                        "invalid shape"
                        if payload is None
                        else (
                            f"answer={payload.get('answer')!r}, "
                            f"sources={len(payload['sources'])}, "
                            f"citations={len(payload['citations'])}"
                        ),
                    ),
                )

            synthesis = self._call(
                synthesis_route[0],
                synthesis_route[1],
                token=token,
                json=synthesis_route[2],
            )
            if synthesis.status_code != 200:
                self.gaps.append(
                    Gap(
                        "PEDR1B-SCOPE-STATUS",
                        role,
                        synthesis_route[0],
                        synthesis_route[1],
                        "200",
                        str(synthesis.status_code),
                    )
                )
            else:
                try:
                    payload = self._synthesis_payload(synthesis)
                except Exception:  # pragma: no cover - real HTTP adapters vary
                    payload = None
                safe = (
                    payload is not None
                    and payload["content"] == _SYNTHESIS_EMPTY_CONTENT
                    and payload["citations"] == []
                    and payload["chunk_count"] == 0
                )
                self._record(
                    safe,
                    Gap(
                        "SYNTHESIS-SCOPE-LEAK",
                        role,
                        synthesis_route[0],
                        synthesis_route[1],
                        "zero chunks and citations",
                        "invalid shape"
                        if payload is None
                        else (
                            f"content={payload['content']!r}, "
                            f"chunk_count={payload['chunk_count']!r}, "
                            f"citations={len(payload['citations'])}"
                        ),
                    ),
                )

            facets = self._call(
                facets_route[0],
                facets_route[1],
                token=token,
                json=facets_route[2],
            )
            if facets.status_code != 200:
                self.gaps.append(
                    Gap(
                        "PEDR1B-SCOPE-STATUS",
                        role,
                        facets_route[0],
                        facets_route[1],
                        "200",
                        str(facets.status_code),
                    )
                )
                continue
            facet_ids = self._facet_project_ids(facets)
            facet_safe = (
                self._facets_are_empty(facets)
                and facet_ids == set()
                and accessible_ids is not None
            )
            self._record(
                facet_safe,
                Gap(
                    "FACET-SCOPE-LEAK",
                    role,
                    facets_route[0],
                    facets_route[1],
                    "all facet aggregates empty for inaccessible project",
                    "invalid shape"
                    if facet_ids is None
                    else f"facet_projects={sorted(facet_ids)}",
                ),
            )

    @staticmethod
    def _json_object(response: Any) -> dict[str, Any] | None:
        try:
            payload = response.json()
        except Exception:  # pragma: no cover - real HTTP adapters vary
            return None
        return payload if isinstance(payload, dict) else None

    @classmethod
    def _alternate_search_is_empty(cls, response: Any) -> bool:
        """Require the full RAG + semantic envelope to carry no foreign content."""
        payload = cls._json_object(response)
        if payload is None:
            return False
        rag = payload.get("rag")
        semantic = payload.get("semantic")
        return (
            isinstance(rag, dict)
            and rag.get("answer") == _RAG_EMPTY_ANSWER
            and rag.get("sources") == []
            and rag.get("citations") == []
            and isinstance(semantic, dict)
            and semantic.get("results") == []
        )

    @classmethod
    def _history_entries(cls, response: Any) -> list[dict[str, Any]] | None:
        payload = cls._json_object(response)
        entries = payload.get("entries") if payload is not None else None
        if not isinstance(entries, list) or not all(
            isinstance(entry, dict) for entry in entries
        ):
            return None
        return entries

    def _record_exact_deny(
        self,
        response: Any,
        *,
        role: str,
        method: str,
        path: str,
        expected: int,
        kind: str,
    ) -> None:
        actual = response.status_code
        if 200 <= actual < 300:
            self.gaps.append(
                Gap("DENY-LEAK-2xx", role, method, path, str(expected), str(actual))
            )
        elif actual != expected:
            self.gaps.append(
                Gap(kind, role, method, path, str(expected), str(actual))
            )

    def _cleanup_created(
        self,
        *,
        label: str,
        method: str,
        path: str,
        token: str,
    ) -> None:
        try:
            response = self._call(method, path, token=token)
        except Exception as exc:  # pragma: no cover - exercised by live transport
            self.teardown_failures.append(
                f"{label}: {method.upper()} {path} raised {type(exc).__name__}: {exc}"
            )
            return
        if not 200 <= response.status_code < 300:
            self.teardown_failures.append(
                f"{label}: {method.upper()} {path} -> {response.status_code} "
                f"{getattr(response, 'text', '')}"
            )

    def _pedr1c_owner_fixtures(
        self,
        *,
        owner_token: str,
        expected_owner_id: str,
        project_id: str,
    ) -> tuple[dict[str, str | None], str | None]:
        """Create per-role foreign saved searches and locate owner-positive history."""
        saved_path = f"{self._prefix}/saved-searches"
        owner_saved_ids: dict[str, str | None] = {}
        for deny_role in ("member", "viewer"):
            saved = self._call(
                "post",
                saved_path,
                token=owner_token,
                json={
                    "name": self._tagged(
                        f"foreign for {deny_role} {uuid.uuid4().hex[:8]}"
                    ),
                    "query_text": _PEDR_SCOPE_QUERY,
                    "search_mode": "semantic",
                    "filters": {"project_id": project_id},
                    "top_k": 1,
                },
            )
            saved_payload = self._json_object(saved)
            owner_saved_id = (
                str(saved_payload.get("id"))
                if 200 <= saved.status_code < 300
                and saved_payload is not None
                and saved_payload.get("id")
                else None
            )
            owner_saved_ids[deny_role] = owner_saved_id
            if saved.status_code != 201 or owner_saved_id is None:
                self.gaps.append(
                    Gap(
                        "PEDR1C-FIXTURE",
                        "setup",
                        "post",
                        saved_path,
                        f"201 saved-search fixture for {deny_role}",
                        str(saved.status_code),
                    )
                )

        history_path = f"{self._prefix}/search/history?limit=100"
        history = self._call("get", history_path, token=owner_token)
        owner_history_id: str | None = None
        entries = self._history_entries(history) if history.status_code == 200 else None
        if entries is not None:
            for entry in entries:
                filters = entry.get("filters")
                if (
                    entry.get("query_text") == _PEDR_SCOPE_QUERY
                    and str(entry.get("owner_id")) == expected_owner_id
                    and isinstance(filters, dict)
                    and str(filters.get("project_id")) == project_id
                ):
                    owner_history_id = str(entry.get("id"))
                    break
        if owner_history_id is None:
            self.gaps.append(
                Gap(
                    "NO-OWNER-HISTORY-FIXTURE",
                    "setup",
                    "get",
                    history_path,
                    "owner-positive history entry",
                    "none found" if entries is not None else "invalid response",
                )
            )
        return owner_saved_ids, owner_history_id

    def _pedr1c_foreign_collection_fixture(
        self,
        *,
        owner_token: str,
        chunk_id: str,
    ) -> str | None:
        """Create a disposable foreign parent collection containing the fixture."""
        collection_path = f"{self._prefix}/collections"
        created = self._call(
            "post",
            collection_path,
            token=owner_token,
            json={
                "name": self._tagged(
                    f"foreign parent {uuid.uuid4().hex[:8]}"
                )
            },
        )
        payload = self._json_object(created)
        collection_id = (
            str(payload.get("id"))
            if 200 <= created.status_code < 300
            and payload is not None
            and payload.get("id")
            else None
        )
        if created.status_code != 201 or collection_id is None:
            self.gaps.append(
                Gap(
                    "PEDR1C-FIXTURE",
                    "setup",
                    "post",
                    collection_path,
                    "201 foreign collection fixture",
                    str(created.status_code),
                )
            )
        if collection_id is None:
            return None

        child_path = f"{collection_path}/{collection_id}/chunks"
        added = self._call(
            "post",
            child_path,
            token=owner_token,
            json={"chunk_id": chunk_id},
        )
        if added.status_code != 201:
            self.gaps.append(
                Gap(
                    "PEDR1C-FIXTURE",
                    "setup",
                    "post",
                    child_path,
                    "201 foreign parent child",
                    str(added.status_code),
                )
            )
        return collection_id

    def _pedr1c_saved_history_role(
        self,
        *,
        role: str,
        token: str,
        project_id: str,
        owner_saved_id: str | None,
        owner_history_id: str | None,
    ) -> None:
        saved_path = f"{self._prefix}/saved-searches"
        create = self._call(
            "post",
            saved_path,
            token=token,
            json={
                "name": self._tagged(
                    f"{role} alternate {uuid.uuid4().hex[:8]}"
                ),
                "query_text": _PEDR_SCOPE_QUERY,
                "search_mode": "semantic",
                "filters": {"project_id": project_id},
                "top_k": 1,
            },
        )
        payload = self._json_object(create)
        saved_id = (
            str(payload.get("id"))
            if 200 <= create.status_code < 300
            and payload is not None
            and payload.get("id")
            else None
        )
        if create.status_code != 201 or saved_id is None:
            self.gaps.append(
                Gap(
                    "PEDR1C-SETUP",
                    role,
                    "post",
                    saved_path,
                    "201",
                    str(create.status_code),
                )
            )
        if saved_id is None:
            return

        try:
            listed = self._call("get", saved_path, token=token)
            listed_payload = self._json_object(listed)
            items = listed_payload.get("items") if listed_payload else None
            listed_ids = (
                {str(item.get("id")) for item in items if isinstance(item, dict)}
                if isinstance(items, list)
                else None
            )
            self._record(
                listed.status_code == 200
                and listed_ids is not None
                and saved_id in listed_ids
                and (owner_saved_id is None or owner_saved_id not in listed_ids),
                Gap(
                    "SAVED-SEARCH-OWNER-LEAK",
                    role,
                    "get",
                    saved_path,
                    "only caller-owned saved searches",
                    "invalid response"
                    if listed_ids is None
                    else f"ids={sorted(listed_ids)}",
                ),
            )

            if owner_saved_id is not None:
                cross_saved_path = (
                    f"{self._prefix}/saved-searches/{owner_saved_id}/execute"
                )
                cross_saved = self._call(
                    "post",
                    cross_saved_path,
                    token=token,
                )
                self._record_exact_deny(
                    cross_saved,
                    role=role,
                    method="post",
                    path=cross_saved_path,
                    expected=404,
                    kind="SAVED-SEARCH-OWNER-STATUS",
                )
                cross_update = self._call(
                    "put",
                    cross_saved_path.removesuffix("/execute"),
                    token=token,
                    json={},
                )
                self._record_exact_deny(
                    cross_update,
                    role=role,
                    method="put",
                    path=cross_saved_path.removesuffix("/execute"),
                    expected=404,
                    kind="SAVED-SEARCH-OWNER-STATUS",
                )

            execute_path = f"{self._prefix}/saved-searches/{saved_id}/execute"
            executed = self._call("post", execute_path, token=token)
            self._record(
                executed.status_code == 200
                and self._alternate_search_is_empty(executed),
                Gap(
                    "SAVED-SEARCH-SCOPE-LEAK",
                    role,
                    "post",
                    execute_path,
                    "empty RAG and semantic results",
                    str(executed.status_code),
                ),
            )

            history_path = f"{self._prefix}/search/history?limit=100"
            history = self._call("get", history_path, token=token)
            entries = (
                self._history_entries(history)
                if history.status_code == 200
                else None
            )
            own_history: dict[str, Any] | None = None
            if entries is not None:
                for entry in entries:
                    metadata = entry.get("metadata")
                    if (
                        isinstance(metadata, dict)
                        and str(metadata.get("saved_search_id")) == saved_id
                    ):
                        own_history = entry
                        break
            history_safe = (
                entries is not None
                and own_history is not None
                and own_history.get("result_count") == 0
                and own_history.get("top_chunks") == []
                and (
                    owner_history_id is None
                    or all(str(entry.get("id")) != owner_history_id for entry in entries)
                )
            )
            self._record(
                history.status_code == 200 and history_safe,
                Gap(
                    "SEARCH-HISTORY-OWNER-LEAK",
                    role,
                    "get",
                    history_path,
                    "only caller-owned, redacted empty history",
                    "invalid or leaking response",
                ),
            )

            if own_history is not None:
                replay_path = (
                    f"{self._prefix}/search/replay/{own_history.get('id')}"
                )
                replay = self._call("post", replay_path, token=token)
                replay_payload = self._json_object(replay)
                replay_entry = (
                    replay_payload.get("entry")
                    if replay_payload is not None
                    else None
                )
                self._record(
                    replay.status_code == 200
                    and self._alternate_search_is_empty(replay)
                    and isinstance(replay_entry, dict)
                    and replay_entry.get("result_count") == 0
                    and replay_entry.get("top_chunks") == [],
                    Gap(
                        "SEARCH-REPLAY-SCOPE-LEAK",
                        role,
                        "post",
                        replay_path,
                        "empty replay with redacted entry",
                        str(replay.status_code),
                    ),
                )

            if owner_history_id is not None:
                cross_history_path = (
                    f"{self._prefix}/search/replay/{owner_history_id}"
                )
                cross_history = self._call(
                    "post",
                    cross_history_path,
                    token=token,
                )
                self._record_exact_deny(
                    cross_history,
                    role=role,
                    method="post",
                    path=cross_history_path,
                    expected=404,
                    kind="SEARCH-HISTORY-OWNER-STATUS",
                )
        finally:
            self._cleanup_created(
                label=f"{role} saved search {saved_id}",
                method="delete",
                path=f"{self._prefix}/saved-searches/{saved_id}",
                token=token,
            )

    def _pedr1c_collection_report_role(
        self,
        *,
        role: str,
        token: str,
        privileged_token: str,
        project_id: str,
        chunk_id: str,
        foreign_collection_id: str | None,
    ) -> None:
        collection_path = f"{self._prefix}/collections"
        collection = self._call(
            "post",
            collection_path,
            token=token,
            json={
                "name": self._tagged(
                    f"{role} mixed {uuid.uuid4().hex[:8]}"
                )
            },
        )
        payload = self._json_object(collection)
        collection_id = (
            str(payload.get("id"))
            if 200 <= collection.status_code < 300
            and payload is not None
            and payload.get("id")
            else None
        )
        if collection.status_code != 201 or collection_id is None:
            self.gaps.append(
                Gap(
                    "PEDR1C-SETUP",
                    role,
                    "post",
                    collection_path,
                    "201",
                    str(collection.status_code),
                )
            )
        if collection_id is None:
            return

        report_ids: set[str] = set()
        try:
            if foreign_collection_id is None:
                self.gaps.append(
                    Gap(
                        "PEDR1C-FIXTURE",
                        role,
                        "post",
                        f"{self._prefix}/collections",
                        "foreign parent collection",
                        "not available",
                    )
                )
            else:
                foreign_synthesis_path = f"{self._prefix}/synthesize"
                foreign_synthesis = self._call(
                    "post",
                    foreign_synthesis_path,
                    token=token,
                    json={
                        "collection_id": foreign_collection_id,
                        "format": "summary",
                    },
                )
                self._record_exact_deny(
                    foreign_synthesis,
                    role=role,
                    method="post",
                    path=foreign_synthesis_path,
                    expected=403,
                    kind="SYNTHESIS-FOREIGN-COLLECTION-STATUS",
                )

                foreign_parent_report_path = f"{self._prefix}/reports"
                foreign_parent_report = self._call(
                    "post",
                    foreign_parent_report_path,
                    token=token,
                    json={
                        "title": self._tagged(f"{role} foreign parent"),
                        "collection_id": foreign_collection_id,
                    },
                )
                self._record_exact_deny(
                    foreign_parent_report,
                    role=role,
                    method="post",
                    path=foreign_parent_report_path,
                    expected=403,
                    kind="REPORT-FOREIGN-COLLECTION-STATUS",
                )
                foreign_parent_payload = self._json_object(foreign_parent_report)
                if (
                    200 <= foreign_parent_report.status_code < 300
                    and foreign_parent_payload is not None
                    and foreign_parent_payload.get("id")
                ):
                    report_ids.add(str(foreign_parent_payload["id"]))

            child_path = f"{collection_path}/{collection_id}/chunks"
            denied_add = self._call(
                "post",
                child_path,
                token=token,
                json={"chunk_id": chunk_id},
            )
            self._record_exact_deny(
                denied_add,
                role=role,
                method="post",
                path=child_path,
                expected=403,
                kind="COLLECTION-CHILD-ADD-STATUS",
            )

            secret_note = f"rbac-verify-foreign-{uuid.uuid4().hex}"
            injected = self._call(
                "post",
                child_path,
                token=privileged_token,
                json={"chunk_id": chunk_id, "notes": secret_note},
            )
            if injected.status_code != 201:
                self.gaps.append(
                    Gap(
                        "PEDR1C-FIXTURE",
                        "setup",
                        "post",
                        child_path,
                        "201 privileged mixed-child injection",
                        str(injected.status_code),
                    )
                )
                return
            injected_payload = self._json_object(injected)
            foreign_preview = (
                injected_payload.get("chunk_content")
                if injected_payload is not None
                else None
            )
            if not isinstance(foreign_preview, str) or not foreign_preview:
                self.gaps.append(
                    Gap(
                        "PEDR1C-FIXTURE",
                        "setup",
                        "post",
                        child_path,
                        "foreign chunk preview in injected child response",
                        "missing",
                    )
                )

            detail_path = f"{collection_path}/{collection_id}"
            detail = self._call("get", detail_path, token=token)
            detail_payload = self._json_object(detail)
            self._record(
                detail.status_code == 200
                and detail_payload is not None
                and detail_payload.get("item_count") == 0
                and detail_payload.get("items") == [],
                Gap(
                    "COLLECTION-CHILD-READ-LEAK",
                    role,
                    "get",
                    detail_path,
                    "zero visible children",
                    "invalid or nonempty response",
                ),
            )

            collection_list = self._call("get", collection_path, token=token)
            list_payload = self._json_object(collection_list)
            rows = list_payload.get("data") if list_payload is not None else None
            matching = (
                [
                    row
                    for row in rows
                    if isinstance(row, dict)
                    and str(row.get("id")) == collection_id
                ]
                if isinstance(rows, list)
                else []
            )
            self._record(
                collection_list.status_code == 200
                and len(matching) == 1
                and matching[0].get("item_count") == 0,
                Gap(
                    "COLLECTION-CHILD-COUNT-LEAK",
                    role,
                    "get",
                    collection_path,
                    "caller collection count=0",
                    "missing or nonzero",
                ),
            )

            export_path = f"{detail_path}/export"
            exported = self._call("get", export_path, token=token)
            exported_text = getattr(exported, "text", "")
            self._record(
                exported.status_code == 200
                and "**Total Chunks:** 0" in exported_text
                and secret_note not in exported_text
                and (
                    not isinstance(foreign_preview, str)
                    or foreign_preview not in exported_text
                ),
                Gap(
                    "COLLECTION-CHILD-EXPORT-LEAK",
                    role,
                    "get",
                    export_path,
                    "zero-child export without foreign content",
                    str(exported.status_code),
                ),
            )

            remove_path = f"{child_path}/{chunk_id}"
            denied_remove = self._call("delete", remove_path, token=token)
            self._record_exact_deny(
                denied_remove,
                role=role,
                method="delete",
                path=remove_path,
                expected=404,
                kind="COLLECTION-CHILD-REMOVE-STATUS",
            )

            synthesize_path = f"{self._prefix}/synthesize"
            synthesized = self._call(
                "post",
                synthesize_path,
                token=token,
                json={
                    "collection_id": collection_id,
                    "format": "summary",
                    "save_as_report": True,
                    "report_title": self._tagged(
                        f"{role} mixed synthesis"
                    ),
                },
            )
            synthesized_payload = self._synthesis_payload(synthesized)
            synthesized_report_id = (
                str(synthesized_payload.get("report_id"))
                if 200 <= synthesized.status_code < 300
                and synthesized_payload is not None
                and synthesized_payload.get("report_id")
                else None
            )
            if synthesized_report_id is not None:
                report_ids.add(synthesized_report_id)
            self._record(
                synthesized.status_code == 200
                and synthesized_payload is not None
                and synthesized_payload.get("content") == _SYNTHESIS_EMPTY_CONTENT
                and synthesized_payload.get("citations") == []
                and synthesized_payload.get("chunk_count") == 0
                and synthesized_report_id is not None,
                Gap(
                    "SYNTHESIS-REPORT-SCOPE-LEAK",
                    role,
                    "post",
                    synthesize_path,
                    "empty synthesis with a persisted report",
                    str(synthesized.status_code),
                ),
            )
            if synthesized_report_id is not None:
                persisted_path = (
                    f"{self._prefix}/reports/{synthesized_report_id}"
                )
                persisted = self._call("get", persisted_path, token=token)
                persisted_payload = self._json_object(persisted)
                persisted_sources = (
                    persisted_payload.get("sources")
                    if persisted_payload is not None
                    else None
                )
                collection_only = (
                    isinstance(persisted_sources, list)
                    and len(persisted_sources) == 1
                    and isinstance(persisted_sources[0], dict)
                    and persisted_sources[0].get("source_type") == "collection"
                    and str(persisted_sources[0].get("source_id")) == collection_id
                )
                self._record(
                    persisted.status_code == 200
                    and persisted_payload is not None
                    and persisted_payload.get("content")
                    == _SYNTHESIS_EMPTY_CONTENT
                    and persisted_payload.get("citations") == []
                    and persisted_payload.get("chunk_count") == 0
                    and collection_only,
                    Gap(
                        "SYNTHESIS-REPORT-PERSISTENCE-LEAK",
                        role,
                        "get",
                        persisted_path,
                        "zero chunks and collection-only provenance",
                        str(persisted.status_code),
                    ),
                )

            foreign_synthesis_target = self._call(
                "post",
                synthesize_path,
                token=token,
                json={
                    "collection_id": collection_id,
                    "format": "summary",
                    "save_as_report": True,
                    "report_title": self._tagged(
                        f"{role} foreign target synthesis"
                    ),
                    "project_id": project_id,
                },
            )
            self._record_exact_deny(
                foreign_synthesis_target,
                role=role,
                method="post",
                path=synthesize_path,
                expected=403,
                kind="SYNTHESIS-TARGET-PROJECT-STATUS",
            )
            foreign_synthesis_payload = self._json_object(
                foreign_synthesis_target
            )
            if (
                200 <= foreign_synthesis_target.status_code < 300
                and foreign_synthesis_payload is not None
                and foreign_synthesis_payload.get("report_id")
            ):
                report_ids.add(str(foreign_synthesis_payload["report_id"]))

            report_specs = [
                (
                    "direct",
                    {
                        "title": self._tagged(f"{role} direct foreign"),
                        "chunk_ids": [chunk_id],
                    },
                ),
                (
                    "collection",
                    {
                        "title": self._tagged(f"{role} mixed collection"),
                        "collection_id": collection_id,
                    },
                ),
            ]
            for source_kind, body in report_specs:
                created = self._call(
                    "post",
                    f"{self._prefix}/reports",
                    token=token,
                    json=body,
                )
                created_payload = self._json_object(created)
                report_id = (
                    str(created_payload.get("id"))
                    if 200 <= created.status_code < 300
                    and created_payload is not None
                    and created_payload.get("id")
                    else None
                )
                clean_created = (
                    created.status_code == 201
                    and report_id is not None
                    and created_payload.get("content") == _SYNTHESIS_EMPTY_CONTENT
                    and created_payload.get("citations") == []
                )
                self._record(
                    clean_created,
                    Gap(
                        "REPORT-SOURCE-SCOPE-LEAK",
                        role,
                        "post",
                        f"{self._prefix}/reports",
                        f"empty {source_kind} report",
                        str(created.status_code),
                    ),
                )
                if report_id is None:
                    continue
                report_ids.add(report_id)
                report_path = f"{self._prefix}/reports/{report_id}"
                report = self._call("get", report_path, token=token)
                report_payload = self._json_object(report)
                sources = (
                    report_payload.get("sources")
                    if report_payload is not None
                    else None
                )
                source_persistence_safe = sources == []
                if source_kind == "collection":
                    source_persistence_safe = (
                        isinstance(sources, list)
                        and len(sources) == 1
                        and isinstance(sources[0], dict)
                        and sources[0].get("source_type") == "collection"
                        and str(sources[0].get("source_id")) == collection_id
                    )
                self._record(
                    report.status_code == 200
                    and report_payload is not None
                    and report_payload.get("content") == _SYNTHESIS_EMPTY_CONTENT
                    and report_payload.get("citations") == []
                    and report_payload.get("chunk_count") == 0
                    and source_persistence_safe,
                    Gap(
                        "REPORT-SOURCE-PERSISTENCE-LEAK",
                        role,
                        "get",
                        report_path,
                        "no persisted chunk sources",
                        str(report.status_code),
                    ),
                )

            foreign_target_path = f"{self._prefix}/reports"
            foreign_target = self._call(
                "post",
                foreign_target_path,
                token=token,
                json={
                    "title": self._tagged(f"{role} foreign project"),
                    "chunk_ids": [chunk_id],
                    "project_id": project_id,
                },
            )
            self._record_exact_deny(
                foreign_target,
                role=role,
                method="post",
                path=foreign_target_path,
                expected=403,
                kind="REPORT-TARGET-PROJECT-STATUS",
            )
            foreign_target_payload = self._json_object(foreign_target)
            if (
                200 <= foreign_target.status_code < 300
                and foreign_target_payload is not None
                and foreign_target_payload.get("id")
            ):
                report_ids.add(str(foreign_target_payload["id"]))

            ambiguous = self._call(
                "post",
                foreign_target_path,
                token=token,
                json={
                    "title": self._tagged(f"{role} ambiguous source"),
                    "chunk_ids": [chunk_id],
                    "collection_id": collection_id,
                },
            )
            self._record(
                ambiguous.status_code == 422,
                Gap(
                    "REPORT-SOURCE-VALIDATION",
                    role,
                    "post",
                    foreign_target_path,
                    "422",
                    str(ambiguous.status_code),
                ),
            )
            ambiguous_payload = self._json_object(ambiguous)
            if (
                200 <= ambiguous.status_code < 300
                and ambiguous_payload is not None
                and ambiguous_payload.get("id")
            ):
                report_ids.add(str(ambiguous_payload["id"]))
        finally:
            for report_id in report_ids:
                self._cleanup_created(
                    label=f"{role} report {report_id}",
                    method="delete",
                    path=f"{self._prefix}/reports/{report_id}",
                    token=token,
                )
            self._cleanup_created(
                label=f"{role} collection {collection_id}",
                method="delete",
                path=f"{collection_path}/{collection_id}",
                token=token,
            )

    def _discover_disjoint_scope_space(
        self,
        *,
        owner_token: str,
        foreign_project_id: str,
    ) -> tuple[str, str] | None:
        """Find an existing Space whose projects exclude the foreign fixture."""
        foreign = self._call(
            "get",
            f"{self._prefix}/projects/{foreign_project_id}",
            token=owner_token,
        )
        foreign_payload = self._json_object(foreign)
        if foreign.status_code != 200 or foreign_payload is None:
            return None
        foreign_space_id = foreign_payload.get("workspace_id")

        listing = self._call(
            "get",
            f"{self._prefix}/projects?page_size=100",
            token=owner_token,
        )
        listing_payload = self._json_object(listing)
        rows = listing_payload.get("data") if listing_payload else None
        if listing.status_code != 200 or not isinstance(rows, list):
            return None
        for row in rows:
            if not isinstance(row, dict):
                continue
            project_id = row.get("id")
            space_id = row.get("workspace_id")
            if (
                project_id
                and space_id
                and str(project_id) != foreign_project_id
                and str(space_id) != str(foreign_space_id)
            ):
                return str(space_id), str(project_id)
        return None

    def _grant_disjoint_scope(
        self,
        *,
        role: str,
        token: str,
        user_id: str,
        owner_token: str,
        space_id: str,
        accessible_project_id: str,
        foreign_project_id: str,
    ) -> tuple[bool, bool]:
        """Grant and verify a non-empty project scope disjoint from the target."""
        membership_path = f"{self._prefix}/admin/spaces/{space_id}/members"
        granted = self._call(
            "post",
            membership_path,
            token=owner_token,
            json={"user_id": user_id, "role": role},
        )
        if granted.status_code != 201:
            self.gaps.append(
                Gap(
                    "NO-DISJOINT-SCOPE-FIXTURE",
                    role,
                    "post",
                    membership_path,
                    "201 membership grant",
                    str(granted.status_code),
                )
            )
            return False, False

        listing_path = f"{self._prefix}/projects?page_size=100"
        listing = self._call("get", listing_path, token=token)
        payload = self._json_object(listing)
        rows = payload.get("data") if payload else None
        project_ids = (
            {str(row.get("id")) for row in rows if isinstance(row, dict)}
            if isinstance(rows, list)
            else None
        )
        safe = (
            listing.status_code == 200
            and project_ids is not None
            and accessible_project_id in project_ids
            and foreign_project_id not in project_ids
        )
        self._record(
            safe,
            Gap(
                "NO-DISJOINT-SCOPE-FIXTURE",
                role,
                "get",
                listing_path,
                "non-empty scope excluding foreign fixture",
                "invalid response"
                if project_ids is None
                else f"ids={sorted(project_ids)}",
            ),
        )
        return True, safe

    def _revoke_disjoint_scope(
        self,
        *,
        role: str,
        user_id: str,
        owner_token: str,
        space_id: str,
    ) -> None:
        path = f"{self._prefix}/admin/spaces/{space_id}/members/{user_id}"
        try:
            response = self._call("delete", path, token=owner_token)
        except Exception as exc:  # pragma: no cover - exercised by live transport
            self.teardown_failures.append(
                f"{role} temporary Space membership: DELETE {path} raised "
                f"{type(exc).__name__}: {exc}"
            )
            return
        if not 200 <= response.status_code < 300:
            self.teardown_failures.append(
                f"{role} temporary Space membership: DELETE {path} -> "
                f"{response.status_code} {getattr(response, 'text', '')}"
            )

    def pedr1c_scope_matrix(
        self,
        principals: dict[str, str],
        principal_ids: dict[str, str] | None = None,
    ) -> None:
        """Prove alternate artifact and collection-child paths cannot bypass scope."""
        if self._pedr1b_fixture is None:
            self.gaps.append(
                Gap(
                    "NO-PEDR1C-FIXTURE",
                    "setup",
                    "post",
                    f"{self._prefix}/search",
                    "owner-positive PEDR-1B fixture",
                    "not available",
                )
            )
            return
        owner_role = self._pedr1b_fixture_owner_role
        owner_token = principals.get(owner_role or "")
        if owner_role != "second_owner" or not owner_token:
            self.gaps.append(
                Gap(
                    "NO-DISPOSABLE-OWNER",
                    "setup",
                    "post",
                    f"{self._prefix}/admin/users",
                    "throwaway second-owner fixture principal",
                    owner_role or "none",
                )
            )
            return

        project_id, chunk_id = self._pedr1b_fixture
        principal_ids = principal_ids or self._principal_ids
        expected_owner_id = principal_ids.get("second_owner")
        if not expected_owner_id:
            self.gaps.append(
                Gap(
                    "NO-DISPOSABLE-OWNER",
                    "setup",
                    "post",
                    f"{self._prefix}/admin/users",
                    "throwaway second-owner fixture principal UUID",
                    "missing",
                )
            )
            return
        disjoint_scope = self._discover_disjoint_scope_space(
            owner_token=owner_token,
            foreign_project_id=project_id,
        )
        if disjoint_scope is None:
            self.gaps.append(
                Gap(
                    "NO-DISJOINT-SCOPE-FIXTURE",
                    "setup",
                    "get",
                    f"{self._prefix}/projects?page_size=100",
                    "an existing non-empty Space scope disjoint from the foreign project",
                    "none found",
                )
            )
            return
        space_id, accessible_project_id = disjoint_scope

        owner_saved_ids: dict[str, str | None] = {}
        owner_saved_deleted_by_probe: set[str] = set()
        foreign_collection_id: str | None = None
        temporary_memberships: list[tuple[str, str]] = []
        try:
            owner_saved_ids, owner_history_id = self._pedr1c_owner_fixtures(
                owner_token=owner_token,
                expected_owner_id=expected_owner_id,
                project_id=project_id,
            )
            foreign_collection_id = self._pedr1c_foreign_collection_fixture(
                owner_token=owner_token,
                chunk_id=chunk_id,
            )
            for role in ("member", "viewer"):
                token = principals.get(role)
                user_id = principal_ids.get(role)
                if not token or not user_id:
                    self.gaps.append(
                        Gap(
                            "NO-DISJOINT-SCOPE-FIXTURE",
                            role,
                            "post",
                            f"{self._prefix}/admin/spaces/{space_id}/members",
                            "authenticated principal UUID",
                            "missing token or user id",
                        )
                    )
                    continue
                granted, scope_safe = self._grant_disjoint_scope(
                    role=role,
                    token=token,
                    user_id=user_id,
                    owner_token=owner_token,
                    space_id=space_id,
                    accessible_project_id=accessible_project_id,
                    foreign_project_id=project_id,
                )
                if granted:
                    temporary_memberships.append((role, user_id))
                if not scope_safe:
                    continue
                owner_saved_id = owner_saved_ids.get(role)
                self._pedr1c_saved_history_role(
                    role=role,
                    token=token,
                    project_id=project_id,
                    owner_saved_id=owner_saved_id,
                    owner_history_id=owner_history_id,
                )
                if owner_saved_id is not None:
                    owner_saved_path = (
                        f"{self._prefix}/saved-searches/{owner_saved_id}"
                    )
                    cross_delete = self._call(
                        "delete",
                        owner_saved_path,
                        token=token,
                    )
                    self._record_exact_deny(
                        cross_delete,
                        role=role,
                        method="delete",
                        path=owner_saved_path,
                        expected=404,
                        kind="SAVED-SEARCH-OWNER-STATUS",
                    )
                    if 200 <= cross_delete.status_code < 300:
                        owner_saved_deleted_by_probe.add(owner_saved_id)
                self._pedr1c_collection_report_role(
                    role=role,
                    token=token,
                    privileged_token=owner_token,
                    project_id=project_id,
                    chunk_id=chunk_id,
                    foreign_collection_id=foreign_collection_id,
                )
        finally:
            if foreign_collection_id is not None:
                self._cleanup_created(
                    label=f"second-owner collection {foreign_collection_id}",
                    method="delete",
                    path=f"{self._prefix}/collections/{foreign_collection_id}",
                    token=owner_token,
                )
            for owner_saved_id in owner_saved_ids.values():
                if (
                    owner_saved_id is not None
                    and owner_saved_id not in owner_saved_deleted_by_probe
                ):
                    self._cleanup_created(
                        label=f"second-owner saved search {owner_saved_id}",
                        method="delete",
                        path=f"{self._prefix}/saved-searches/{owner_saved_id}",
                        token=owner_token,
                    )
            for role, user_id in reversed(temporary_memberships):
                self._revoke_disjoint_scope(
                    role=role,
                    user_id=user_id,
                    owner_token=owner_token,
                    space_id=space_id,
                )

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

    def seeded_matrix(
        self,
        spec: SeedSpec,
        resource_id: str,
        principals: dict[str, str],
        *,
        live_safe: bool = False,
    ) -> None:
        """member/viewer -> denied on every per-id route; owner/second-owner -> 2xx
        on the canonical GET (over-blocking guard).

        Every authenticated deny must be the exact 403 contract. Valid request bodies
        keep 401/404/422/5xx from masquerading as authorization enforcement. The
        seeded mission is completed and has no result payload, so even a fail-open
        submit/promote probe fails a safe precondition before any queue/provider work.
        """
        routes = spec.routes
        if live_safe:
            routes = [
                (method, path)
                for method, path in routes
                if (
                    spec.name,
                    method,
                    path.removeprefix(self._prefix),
                )
                not in _LOCAL_ONLY_AUTHZ_ROUTES
            ]
        for role in ("member", "viewer"):
            token = principals.get(role)
            if not token:
                continue
            for method, tmpl in routes:
                path = tmpl.format(id=resource_id)
                resp = self._call(
                    method,
                    path,
                    token=token,
                    json=self._body_for(method, path),
                )
                self._record_exact_deny(
                    resp,
                    role=role,
                    method=method,
                    path=path,
                    expected=403,
                    kind=f"{spec.name.upper()}-AUTHZ-STATUS",
                )
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
            self._record_exact_deny(
                resp,
                role=role,
                method="post",
                path=path,
                expected=403,
                kind="SERVICE-LOG-AUTHZ-STATUS",
            )
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
        try:
            resp = self._call(spec.delete_method, path, api_key=owner_key)
        except Exception as exc:  # pragma: no cover - exercised by live transport
            self.teardown_failures.append(
                f"{spec.name} {resource_id}: {spec.delete_method.upper()} {path} "
                f"raised {type(exc).__name__}: {exc}"
            )
            return
        if not (200 <= resp.status_code < 300):
            self.teardown_failures.append(
                f"{spec.name} {resource_id}: {spec.delete_method.upper()} {path} -> {resp.status_code} {resp.text}"
            )

    def purge_user(self, owner_key: str, user_id: str) -> None:
        path = f"{self._prefix}/admin/users/{user_id}"
        try:
            resp = self._call("delete", path, api_key=owner_key)
        except Exception as exc:  # pragma: no cover - exercised by live transport
            self.teardown_failures.append(
                f"user {user_id}: DELETE {path} raised {type(exc).__name__}: {exc}"
            )
            return
        if not (200 <= resp.status_code < 300):
            self.teardown_failures.append(
                f"user {user_id}: DELETE /admin/users/{user_id} -> {resp.status_code} {resp.text}"
            )

    def delete_api_key(self, token: str, key_id: str) -> None:
        """Delete the owner's run key so a run never leaks a tl_ key (the owner is
        capped at 10). Authenticated with the owner JWT, not the key itself, so it
        works even as the very last teardown step."""
        path = f"{self._prefix}/auth/api-keys/{key_id}"
        try:
            resp = self._call("delete", path, token=token)
        except Exception as exc:  # pragma: no cover - exercised by live transport
            self.teardown_failures.append(
                f"owner api-key {key_id}: DELETE {path} raised "
                f"{type(exc).__name__}: {exc}"
            )
            return
        if not (200 <= resp.status_code < 300):
            self.teardown_failures.append(
                f"owner api-key {key_id}: DELETE /auth/api-keys/{key_id} -> {resp.status_code} {resp.text}"
            )

    def reconcile_tagged_artifacts(self, owner_token: str) -> None:
        """Find and delete every run-tagged artifact before throwaway-user purge.

        A create can commit remotely while its response times out or omits an id.
        Collection/report ownership FKs use ``SET NULL``, so purging the user is not
        cleanup. The privileged owner lists by the unique run tag, deletes matches,
        then lists again; an unreadable or nonempty final list is a teardown failure.
        """

        def _list_tagged(
            *,
            label: str,
            path: str,
            rows_field: str,
            name_field: str,
            paginated: bool = False,
            pagination_field: str | None = None,
        ) -> list[dict[str, Any]] | None:
            matches: list[dict[str, Any]] = []
            page = 1
            while True:
                request_path = (
                    f"{path}?page={page}&page_size=100" if paginated else path
                )
                try:
                    response = self._call("get", request_path, token=owner_token)
                except Exception as exc:  # pragma: no cover - live transport
                    self.teardown_failures.append(
                        f"{label} reconciliation: GET {request_path} raised "
                        f"{type(exc).__name__}: {exc}"
                    )
                    return None
                payload = self._json_object(response)
                rows = payload.get(rows_field) if payload is not None else None
                if response.status_code != 200 or not isinstance(rows, list):
                    self.teardown_failures.append(
                        f"{label} reconciliation: GET {request_path} -> "
                        f"{response.status_code} invalid list response"
                    )
                    return None
                for row in rows:
                    if (
                        isinstance(row, dict)
                        and str(row.get(name_field, "")).startswith(self._run_tag)
                    ):
                        matches.append(row)
                if not paginated:
                    break
                pagination = (
                    payload.get(pagination_field)
                    if pagination_field is not None
                    else payload
                )
                total = (
                    pagination.get("total")
                    if isinstance(pagination, dict)
                    else None
                )
                if not isinstance(total, int):
                    self.teardown_failures.append(
                        f"{label} reconciliation: GET {request_path} missing integer total"
                    )
                    return None
                if page * 100 >= total:
                    break
                page += 1
            return matches

        artifact_specs = (
            (
                "saved search",
                f"{self._prefix}/saved-searches",
                "items",
                "name",
                False,
                None,
                f"{self._prefix}/saved-searches/{{id}}",
            ),
            (
                "collection",
                f"{self._prefix}/collections",
                "data",
                "name",
                False,
                None,
                f"{self._prefix}/collections/{{id}}",
            ),
            (
                "report",
                f"{self._prefix}/reports",
                "items",
                "title",
                True,
                None,
                f"{self._prefix}/reports/{{id}}",
            ),
            (
                "mission",
                f"{self._prefix}/missions",
                "data",
                "title",
                True,
                "pagination",
                f"{self._prefix}/missions/{{id}}",
            ),
        )
        for (
            label,
            path,
            rows_field,
            name_field,
            paginated,
            pagination_field,
            delete_path,
        ) in artifact_specs:
            matches = _list_tagged(
                label=label,
                path=path,
                rows_field=rows_field,
                name_field=name_field,
                paginated=paginated,
                pagination_field=pagination_field,
            )
            if matches is None:
                continue
            for row in matches:
                artifact_id = row.get("id")
                if not artifact_id:
                    self.teardown_failures.append(
                        f"{label} reconciliation: tagged list row missing id"
                    )
                    continue
                target = delete_path.format(id=artifact_id)
                try:
                    deleted = self._call("delete", target, token=owner_token)
                except Exception as exc:  # pragma: no cover - live transport
                    self.teardown_failures.append(
                        f"{label} reconciliation: DELETE {target} raised "
                        f"{type(exc).__name__}: {exc}"
                    )
                    continue
                if not 200 <= deleted.status_code < 300:
                    self.teardown_failures.append(
                        f"{label} reconciliation: DELETE {target} -> "
                        f"{deleted.status_code} {getattr(deleted, 'text', '')}"
                    )

            remaining = _list_tagged(
                label=label,
                path=path,
                rows_field=rows_field,
                name_field=name_field,
                paginated=paginated,
                pagination_field=pagination_field,
            )
            if remaining:
                remaining_ids = sorted(str(row.get("id")) for row in remaining)
                self.teardown_failures.append(
                    f"{label} reconciliation left tagged ids: {remaining_ids}"
                )

    def reconcile_tagged_api_keys(self, owner_token: str) -> None:
        """Delete every owner API key carrying this run's tag, then verify absence."""
        path = f"{self._prefix}/auth/api-keys"

        def _list() -> list[dict[str, Any]] | None:
            try:
                response = self._call("get", path, token=owner_token)
            except Exception as exc:  # pragma: no cover - live transport
                self.teardown_failures.append(
                    f"api-key reconciliation: GET {path} raised "
                    f"{type(exc).__name__}: {exc}"
                )
                return None
            payload = self._json_object(response)
            rows = payload.get("keys") if payload is not None else None
            if response.status_code != 200 or not isinstance(rows, list):
                self.teardown_failures.append(
                    f"api-key reconciliation: GET {path} -> "
                    f"{response.status_code} invalid list response"
                )
                return None
            return [
                row
                for row in rows
                if isinstance(row, dict)
                and str(row.get("name", "")).startswith(self._run_tag)
            ]

        matches = _list()
        if matches is None:
            return
        for row in matches:
            key_id = row.get("id")
            target = f"{path}/{key_id}"
            try:
                response = self._call("delete", target, token=owner_token)
            except Exception as exc:  # pragma: no cover - live transport
                self.teardown_failures.append(
                    f"api-key reconciliation: DELETE {target} raised "
                    f"{type(exc).__name__}: {exc}"
                )
                continue
            if not 200 <= response.status_code < 300:
                self.teardown_failures.append(
                    f"api-key reconciliation: DELETE {target} -> "
                    f"{response.status_code} {getattr(response, 'text', '')}"
                )
        remaining = _list()
        if remaining:
            self.teardown_failures.append(
                "api-key reconciliation left tagged ids: "
                f"{sorted(str(row.get('id')) for row in remaining)}"
            )

    def reconcile_throwaway_users(self, owner_token: str) -> None:
        """Hard-delete response-lost run users and verify none remain."""
        path = f"{self._prefix}/admin/users"
        email_prefix = f"{self._run_tag}-"

        def _list() -> list[dict[str, Any]] | None:
            try:
                response = self._call("get", path, token=owner_token)
            except Exception as exc:  # pragma: no cover - live transport
                self.teardown_failures.append(
                    f"user reconciliation: GET {path} raised "
                    f"{type(exc).__name__}: {exc}"
                )
                return None
            try:
                rows = response.json()
            except Exception:  # pragma: no cover - live adapters vary
                rows = None
            if response.status_code != 200 or not isinstance(rows, list):
                self.teardown_failures.append(
                    f"user reconciliation: GET {path} -> "
                    f"{response.status_code} invalid list response"
                )
                return None
            return [
                row
                for row in rows
                if isinstance(row, dict)
                and str(row.get("email", "")).startswith(email_prefix)
            ]

        matches = _list()
        if matches is None:
            return
        for row in matches:
            user_id = row.get("id")
            target = f"{path}/{user_id}"
            try:
                response = self._call("delete", target, token=owner_token)
            except Exception as exc:  # pragma: no cover - live transport
                self.teardown_failures.append(
                    f"user reconciliation: DELETE {target} raised "
                    f"{type(exc).__name__}: {exc}"
                )
                continue
            if not 200 <= response.status_code < 300:
                self.teardown_failures.append(
                    f"user reconciliation: DELETE {target} -> "
                    f"{response.status_code} {getattr(response, 'text', '')}"
                )
        remaining = _list()
        if remaining:
            self.teardown_failures.append(
                "user reconciliation left run emails: "
                f"{sorted(str(row.get('email')) for row in remaining)}"
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
        self._principal_ids = {}
        self._run_tag = f"rbac-verify-{uuid.uuid4().hex}"
        owner_token = self.login(owner_email, owner_password)
        try:
            owner_key, _owner_key_id = self.mint_api_key(owner_token)
            self.precheck_rbac_status(owner_key)

            self.check_coverage()  # every wired route must be seeded or anon-only

            self._log("anon-401 sweep across every per-id route...")
            self.anon_sweep()
            self._log("anon-401 sweep across PEDR/retrieval scope routes...")
            self.pedr_anon_sweep()
            self._log("anon-401 sweep across RAG/synthesis/facet scope routes...")
            self.pedr1b_anon_sweep()
            self._log("anon-401 sweep across alternate artifact routes...")
            self.pedr1c_anon_sweep()

            provisioned: list[str] = []
            seeded: list[tuple[SeedSpec, str]] = []
            principals: dict[str, str] = {"owner": owner_token}
            try:
                for role in ("member", "viewer", "owner", "service"):
                    pname = "second_owner" if role == "owner" else role
                    created = self.create_throwaway_user(
                        owner_key,
                        role,
                        self._run_tag,
                    )
                    if not created:
                        continue
                    uid, email = created
                    provisioned.append(uid)  # track for teardown BEFORE login
                    self._principal_ids[pname] = uid
                    try:
                        principals[pname] = self.login(email, _THROWAWAY_PASSWORD)
                    except HarnessError as exc:
                        self.notes.append(f"provisioned {role} ({uid}) but login failed: {exc}")
                self._log(f"provisioned principals: {sorted(p for p in principals if p != 'owner')}")
                # Both deny tiers are mandatory. Missing either one would silently
                # remove half of the role matrix and make a green run ambiguous.
                for required_role in ("member", "viewer"):
                    if required_role not in principals:
                        self.gaps.append(
                            Gap(
                                "NO-DENY-PRINCIPAL",
                                required_role,
                                "post",
                                f"{self._prefix}/admin/users",
                                f"{required_role} provisioned and logged in",
                                "missing — role matrix did not run",
                            )
                        )

                specs = _seed_specs(self._prefix, run_tag=self._run_tag)
                project_spec = next(
                    spec for spec in specs if spec.name == "project"
                )
                project_id = self.discover_owned_project(owner_token)
                ctx: dict[str, Any] = {"project": project_id}
                self._log(
                    f"reusing owner project={project_id}; running non-destructive "
                    "authz matrix..."
                )
                self.seeded_matrix(
                    project_spec,
                    project_id,
                    principals,
                    live_safe=True,
                )

                for spec in specs:
                    if spec.name == "project":
                        continue
                    rid = self.seed(owner_key, spec, ctx)
                    if rid is None:
                        continue
                    ctx[spec.name] = rid
                    seeded.append((spec, rid))
                    self._log(f"seeded {spec.name}={rid}; running authz matrix...")
                    self.seeded_matrix(spec, rid, principals, live_safe=True)

                self.list_isolation_check(ctx["project"], principals)
                self._log("PEDR/retrieval tenant-scope matrix...")
                self.pedr_scope_matrix(ctx["project"], principals)

                self._log("RAG/synthesis/facet tenant-scope matrix...")
                self.pedr1b_scope_matrix(principals)
                self._log(
                    "saved-search/history/report/collection-child scope matrix..."
                )
                self.pedr1c_scope_matrix(principals, self._principal_ids)

                if "mission" in ctx:
                    self._log("service-role log-ingest gate (POST .../logs)...")
                    self.service_log_write_matrix(ctx["mission"], principals)

                self.notes.append(
                    "authz matrix reuses a validated owner project and seeds only "
                    "hard-deletable collection/mission fixtures; project DELETE is "
                    "local-only (live anonymous 401 coverage retained); "
                    f"{len(_ANON_ONLY_ROUTES)} per-id routes remain in the explicit "
                    "anon registry; reports/collection children also receive PEDR-1C "
                    "cross-tenant probes, while document/job routes remain anon-only"
                )
            finally:
                # Children before parents (mission references project); best-effort.
                for spec, rid in reversed(seeded):
                    self.delete_resource(owner_key, spec, rid)
                # A remote create may have committed even when its response timed
                # out or omitted an id. Reconcile by run tag BEFORE user deletion;
                # collection/report owner FKs would otherwise become NULL orphans.
                self.reconcile_tagged_artifacts(owner_token)
                for uid in provisioned:
                    self.purge_user(owner_key, uid)
                self.reconcile_throwaway_users(owner_token)
        finally:
            # The key create may have committed even if its response was lost, so
            # list/delete/re-list by run tag is the authoritative final cleanup.
            self.reconcile_tagged_api_keys(owner_token)

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
            "\nPASS: anon-401 enforced on every per-id and scoped retrieval route + "
            "seeded authz matrix (project/collection/mission/PEDR/RAG/synthesis/"
            "facets/saved-search/history/reports/collection-children) clean; no "
            "leaked cruft."
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
