"""FastAPI application entry point."""

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.v1 import (
    admin,
    auth,
    auth_device,
    cache,
    collections,
    corrections,
    deepsearch,
    documents,
    facets,
    health,
    missions,
    monitoring,
    pedr_preflight,
    pedr_related,
    pedr_search,
    projects,
    qdrant_admin,
    quality,
    quality_automated,
    redaction,
    relationships,
    reports,
    retrieval,
    saved_searches,
    search,
    search_history,
    synthesize,
    webhooks,
)
from app.core.config import settings
from app.core.database import Base, engine
from app.core.qdrant_client import prewarm_qdrant
from app.core.security import require_authenticated_user
from app.onboarding import router as onboarding_router
from app.services.metrics_aggregator import MetricsAggregator, get_metrics_aggregator


class ProxyHeadersMiddleware:
    """Middleware to trust X-Forwarded-Proto header from reverse proxies.

    When running behind Cloudflare/Railway, this ensures FastAPI uses HTTPS
    in redirect URLs instead of HTTP, preventing auth header stripping.
    """

    def __init__(self, app: ASGIApp, trusted_hosts: list[str] | None = None):
        self.app = app
        self.trusted_hosts = trusted_hosts or ["*"]

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope.get("headers", []))

            # Trust X-Forwarded-Proto header to set correct scheme
            forwarded_proto = headers.get(b"x-forwarded-proto", b"").decode("latin-1")
            if forwarded_proto:
                scope["scheme"] = forwarded_proto

            # Trust X-Forwarded-Host if present
            forwarded_host = headers.get(b"x-forwarded-host", b"").decode("latin-1")
            if forwarded_host:
                # Update host header in scope
                scope["headers"] = [
                    (k, v) if k != b"host" else (k, forwarded_host.encode("latin-1"))
                    for k, v in scope.get("headers", [])
                ]

        await self.app(scope, receive, send)


# Create tables in development (use migrations in production)
if settings.environment == "development":
    Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    description="Personal research repository with RAG-powered search",
    version=settings.app_version,
)

templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent / "templates")
)

cors_origins = settings.cors_origins
if not cors_origins:
    raise RuntimeError(
        "No CORS origins configured for the current environment. Set CORS_ALLOWED_ORIGINS_DEV or CORS_ALLOWED_ORIGINS_PROD."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allowed_methods,
    allow_headers=settings.cors_allowed_headers,
)

# Add proxy headers middleware to trust X-Forwarded-* headers from Cloudflare/Railway
# This ensures redirects use HTTPS instead of HTTP, preserving auth headers
app.add_middleware(ProxyHeadersMiddleware)

import logging

logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup_event():
    """Pre-warm Qdrant connection on application startup.

    This eliminates the 60+ second cold-start penalty on the first query
    by initializing the connection pool and running a dummy search.
    """
    logger.info("Pre-warming Qdrant connection...")
    success = await prewarm_qdrant()
    if success:
        logger.info("Qdrant pre-warm complete - ready for queries")
    else:
        logger.warning(
            "Qdrant pre-warm failed - first query may experience cold-start latency. "
            "Check QDRANT_URL configuration and Qdrant service availability."
        )


protected_dependencies = [Depends(require_authenticated_user)]

# Include routers
app.include_router(health.router, prefix=settings.api_v1_prefix, tags=["health"])
app.include_router(
    admin.router,
    prefix=f"{settings.api_v1_prefix}/admin",
    tags=["admin"],
    dependencies=protected_dependencies,
)
app.include_router(
    qdrant_admin.router,
    prefix=f"{settings.api_v1_prefix}/qdrant-admin",
    tags=["qdrant-admin"],
    dependencies=protected_dependencies,
)
app.include_router(
    cache.router,
    prefix=f"{settings.api_v1_prefix}/cache",
    tags=["cache"],
    dependencies=protected_dependencies,
)
app.include_router(
    redaction.router,
    prefix=f"{settings.api_v1_prefix}/redaction",
    tags=["redaction"],
    dependencies=protected_dependencies,
)
app.include_router(
    documents.router,
    prefix=f"{settings.api_v1_prefix}/documents",
    tags=["documents"],
    dependencies=protected_dependencies,
)
app.include_router(
    projects.router,
    prefix=f"{settings.api_v1_prefix}/projects",
    tags=["projects"],
    dependencies=protected_dependencies,
)
app.include_router(
    search.router,
    prefix=settings.api_v1_prefix,
    tags=["search"],
    dependencies=protected_dependencies,
)
app.include_router(
    search_history.router,
    prefix=settings.api_v1_prefix,
    tags=["search-history"],
    dependencies=protected_dependencies,
)
app.include_router(
    saved_searches.router,
    prefix=settings.api_v1_prefix,
    tags=["saved-searches"],
    dependencies=protected_dependencies,
)
app.include_router(
    collections.router,
    prefix=f"{settings.api_v1_prefix}/collections",
    tags=["collections"],
    dependencies=protected_dependencies,
)
app.include_router(
    facets.router,
    prefix=settings.api_v1_prefix,
    tags=["facets"],
    dependencies=protected_dependencies,
)
app.include_router(
    retrieval.router,
    prefix=f"{settings.api_v1_prefix}/retrieval",
    tags=["retrieval"],
    dependencies=protected_dependencies,
)
app.include_router(
    missions.router,
    prefix=f"{settings.api_v1_prefix}/missions",
    tags=["missions"],
    dependencies=protected_dependencies,
)
app.include_router(
    relationships.router,
    prefix=f"{settings.api_v1_prefix}/missions",
    tags=["relationships"],
    dependencies=protected_dependencies,
)
app.include_router(
    deepsearch.router,
    prefix=f"{settings.api_v1_prefix}/deepsearch",
    tags=["deepsearch"],
    dependencies=protected_dependencies,
)
app.include_router(
    corrections.router,
    prefix=f"{settings.api_v1_prefix}/deepsearch",
    tags=["corrections"],
    dependencies=protected_dependencies,
)
app.include_router(
    pedr_preflight.router,
    prefix=f"{settings.api_v1_prefix}/pedr",
    tags=["pedr-preflight"],
    dependencies=protected_dependencies,
)
app.include_router(
    pedr_search.router,
    prefix=settings.api_v1_prefix,
    tags=["pedr-search"],
    dependencies=protected_dependencies,
)
app.include_router(
    pedr_related.router,
    prefix=settings.api_v1_prefix,
    tags=["pedr-related"],
    dependencies=protected_dependencies,
)
app.include_router(
    quality.router,
    prefix=settings.api_v1_prefix,
    tags=["quality"],
    dependencies=protected_dependencies,
)
app.include_router(
    quality_automated.router,
    prefix=f"{settings.api_v1_prefix}/quality/automated",
    tags=["quality-automation"],
    dependencies=protected_dependencies,
)
app.include_router(
    monitoring.router,
    prefix=f"{settings.api_v1_prefix}/monitoring",
    tags=["monitoring"],
    dependencies=protected_dependencies,
)
app.include_router(
    synthesize.router,
    prefix=settings.api_v1_prefix,
    tags=["synthesize"],
    dependencies=protected_dependencies,
)
app.include_router(
    reports.router,
    prefix=f"{settings.api_v1_prefix}/reports",
    tags=["reports"],
    dependencies=protected_dependencies,
)
app.include_router(
    onboarding_router,
    prefix=settings.api_v1_prefix,
    dependencies=protected_dependencies,
)
app.include_router(auth.router, prefix=f"{settings.api_v1_prefix}/auth", tags=["auth"])
# T42.4: device-code endpoints. /code + /token are unauthenticated by design
# (the device_code itself is the bearer secret); /approve, /deny, and
# /grants/{code} require an authenticated web user via the per-route
# Depends(require_authenticated_user).
app.include_router(
    auth_device.router,
    prefix=f"{settings.api_v1_prefix}/auth/device",
    tags=["auth-device"],
)
# Webhooks use signature-based auth, not JWT
app.include_router(
    webhooks.router,
    prefix=f"{settings.api_v1_prefix}/webhooks",
    tags=["webhooks"],
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


@app.get(
    "/admin/dashboard", response_class=HTMLResponse, dependencies=protected_dependencies
)
def admin_dashboard(
    request: Request,
    aggregator: MetricsAggregator = Depends(get_metrics_aggregator),
) -> HTMLResponse:
    """Render the admin dashboard at the requested path."""

    metrics = aggregator.collect()
    auth_header = request.headers.get("authorization", "")
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {"request": request, "metrics": metrics, "auth_header": auth_header},
    )
