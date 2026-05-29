"""Guard against first-match-wins route shadowing (Sprint 43 review follow-up).

FastAPI resolves routes in registration order, so two routes resolving to the
same (method, path) silently shadow each other. The Sprint 43 review found
onboarding's POST /projects and GET /documents/{id} dead-shadowed by the
projects/documents routers. `_assert_no_duplicate_routes` turns that into a
startup failure; these tests lock that behavior in.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.main import _assert_no_duplicate_routes, app


def test_app_has_no_duplicate_routes():
    """The real app must have no two routes resolving to the same (method, path).

    Importing app.main already runs the guard once; calling it again here is an
    explicit, readable assertion that the production app is shadow-free.
    """
    _assert_no_duplicate_routes(app)


def test_guard_detects_duplicate_method_path():
    """The guard raises when two routes share a (method, path)."""
    duped = FastAPI()

    @duped.get("/thing")
    def _first():  # pragma: no cover - body never executed
        return {}

    @duped.get("/thing")
    def _second():  # pragma: no cover - body never executed
        return {}

    with pytest.raises(RuntimeError, match="Duplicate route registrations"):
        _assert_no_duplicate_routes(duped)


def test_guard_allows_same_path_different_methods():
    """Same path with distinct methods is legal and must not trip the guard."""
    app_ok = FastAPI()

    @app_ok.get("/thing")
    def _get():  # pragma: no cover - body never executed
        return {}

    @app_ok.post("/thing")
    def _post():  # pragma: no cover - body never executed
        return {}

    # Should not raise.
    _assert_no_duplicate_routes(app_ok)
