"""Tests for ProxyHeadersMiddleware to ensure HTTPS redirects work correctly."""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.main import ProxyHeadersMiddleware


class TestProxyHeadersMiddleware:
    """Test suite for proxy headers handling."""

    def test_scheme_set_to_https_when_forwarded_proto_is_https(self):
        """Verify the request scheme is set to https when X-Forwarded-Proto is https."""
        app = FastAPI()
        app.add_middleware(ProxyHeadersMiddleware)

        @app.get("/scheme-check")
        async def scheme_check(request: Request):
            return {"scheme": request.url.scheme, "url": str(request.url)}

        client = TestClient(app)
        response = client.get("/scheme-check", headers={"X-Forwarded-Proto": "https"})
        assert response.status_code == 200
        data = response.json()
        assert data["scheme"] == "https", f"Expected https scheme, got: {data}"

    def test_scheme_remains_http_when_no_forwarded_proto(self):
        """Verify scheme remains http when no X-Forwarded-Proto header."""
        app = FastAPI()
        app.add_middleware(ProxyHeadersMiddleware)

        @app.get("/scheme-check")
        async def scheme_check(request: Request):
            return {"scheme": request.url.scheme}

        client = TestClient(app)
        response = client.get("/scheme-check")
        assert response.status_code == 200
        data = response.json()
        # Without forwarded proto, should use default (http for testclient)
        assert data["scheme"] == "http"

    def test_forwarded_host_is_trusted(self):
        """Verify X-Forwarded-Host updates the host header."""
        app = FastAPI()
        app.add_middleware(ProxyHeadersMiddleware)

        @app.get("/host-check")
        async def host_check(request: Request):
            return {"host": request.headers.get("host")}

        client = TestClient(app)
        response = client.get(
            "/host-check", headers={"X-Forwarded-Host": "api.tracelab.aquex.ai"}
        )
        assert response.status_code == 200
        # The middleware should update the host header
        assert response.json()["host"] == "api.tracelab.aquex.ai"

    @pytest.mark.asyncio
    async def test_redirect_location_uses_https_scheme(self):
        """Verify redirect responses use HTTPS in Location header."""
        import httpx

        app = FastAPI(redirect_slashes=True)
        app.add_middleware(ProxyHeadersMiddleware)

        @app.get("/test/")
        async def test_endpoint():
            return {"status": "ok"}

        # Use httpx with ASGITransport for async apps
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get(
                "/test", headers={"X-Forwarded-Proto": "https"}, follow_redirects=False
            )
            assert response.status_code == 307
            location = response.headers.get("location", "")
            assert location.startswith("https://"), (
                f"Expected HTTPS redirect, got: {location}"
            )

    def test_no_redirect_when_trailing_slash_present(self):
        """Verify no redirect when URL has trailing slash."""
        app = FastAPI(redirect_slashes=True)
        app.add_middleware(ProxyHeadersMiddleware)

        @app.get("/test/")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test/", headers={"X-Forwarded-Proto": "https"})
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
