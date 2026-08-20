"""OPS-2: 422 responses must never echo submitted values (credential-leak class).

FastAPI's default RequestValidationError handler includes each error's raw
``input``; a malformed login therefore reflected the submitted password back in
the response body, and downstream consumers persisting bodies is how TraceLab
credentials reached DeepSearch research artifacts.
"""

from fastapi.testclient import TestClient

from app.main import app

SENTINEL = "SENTINEL-NEVER-ECHO-9f2c"


# No context managers: skip startup events (Qdrant prewarm) — the exception
# handler needs no startup state.


def test_login_422_never_echoes_submitted_values():
    # email is type-invalid (dict) → the DEFAULT handler would echo it as
    # 'input', including the sentinel; ours must not.
    resp = TestClient(app).post(
        "/api/v1/auth/login",
        json={"email": {"nested": SENTINEL}, "password": SENTINEL},
    )
    assert resp.status_code == 422
    assert SENTINEL not in resp.text
    for err in resp.json()["detail"]:
        assert set(err) == {"loc", "msg", "type"}


def test_422_keeps_field_locations_usable():
    resp = TestClient(app).post("/api/v1/auth/login", json={})
    assert resp.status_code == 422
    locs = [tuple(err["loc"]) for err in resp.json()["detail"]]
    assert any("email" in loc for loc in locs)
    for err in resp.json()["detail"]:
        assert err["msg"]
        assert err["type"]
        assert "input" not in err


def test_non_auth_route_422_also_sanitized():
    resp = TestClient(app).post(
        "/api/v1/auth/register",
        json={"email": SENTINEL, "password": {"bad": SENTINEL}},
    )
    assert resp.status_code == 422
    assert SENTINEL not in resp.text
