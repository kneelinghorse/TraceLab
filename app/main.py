"""FastAPI application entry point."""
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.v1 import (
    admin,
    auth,
    cache,
    deepsearch,
    documents,
    facets,
    health,
    missions,
    monitoring,
    qdrant_admin,
    projects,
    quality,
    quality_automated,
    redaction,
    retrieval,
    search,
    search_history,
    saved_searches,
)
from app.core.config import settings
from app.core.database import Base, engine
from app.core.security import require_authenticated_user
from app.onboarding import router as onboarding_router
from app.services.metrics_aggregator import MetricsAggregator, get_metrics_aggregator

# Create tables in development (use migrations in production)
if settings.environment == "development":
    Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    description="Personal research repository with RAG-powered search",
    version=settings.app_version,
)

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

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
app.include_router(redaction.router, prefix=f"{settings.api_v1_prefix}/redaction", tags=["redaction"], dependencies=protected_dependencies)
app.include_router(documents.router, prefix=f"{settings.api_v1_prefix}/documents", tags=["documents"], dependencies=protected_dependencies)
app.include_router(projects.router, prefix=f"{settings.api_v1_prefix}/projects", tags=["projects"], dependencies=protected_dependencies)
app.include_router(search.router, prefix=settings.api_v1_prefix, tags=["search"], dependencies=protected_dependencies)
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
app.include_router(facets.router, prefix=settings.api_v1_prefix, tags=["facets"], dependencies=protected_dependencies)
app.include_router(retrieval.router, prefix=f"{settings.api_v1_prefix}/retrieval", tags=["retrieval"], dependencies=protected_dependencies)
app.include_router(missions.router, prefix=f"{settings.api_v1_prefix}/missions", tags=["missions"], dependencies=protected_dependencies)
app.include_router(
    deepsearch.router,
    prefix=f"{settings.api_v1_prefix}/deepsearch",
    tags=["deepsearch"],
    dependencies=protected_dependencies,
)
app.include_router(quality.router, prefix=settings.api_v1_prefix, tags=["quality"], dependencies=protected_dependencies)
app.include_router(
    quality_automated.router,
    prefix=f"{settings.api_v1_prefix}/quality/automated",
    tags=["quality-automation"],
    dependencies=protected_dependencies,
)
app.include_router(monitoring.router, prefix=f"{settings.api_v1_prefix}/monitoring", tags=["monitoring"], dependencies=protected_dependencies)
app.include_router(onboarding_router, prefix=settings.api_v1_prefix, dependencies=protected_dependencies)
app.include_router(auth.router, prefix=f"{settings.api_v1_prefix}/auth", tags=["auth"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": settings.app_name,
        "version": settings.app_version,
        "status": "running"
    }


@app.get("/admin/dashboard", response_class=HTMLResponse, dependencies=protected_dependencies)
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
