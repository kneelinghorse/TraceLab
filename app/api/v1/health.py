"""Health check endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.qdrant_client import get_qdrant_health, is_qdrant_ready
from app.services.reconciler_scheduler import reconciler_health

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check.

    Configuration booleans are deliberately public (DEC#329, owner-approved):
    they disclose posture only, and a false production value is an incident
    state that must be alarmable without credentials. The receipt field proves
    only that this receiver has a secret configured; it cannot prove equality
    with the remote signer's secret. The reconciler block is counts-only (no
    identifiers) for the same reason.

    ``commit`` is the sha this process was deployed from. It is public for the
    same reason and discloses nothing: the repository is public. A post-deploy
    check needs it because Railway reports SUCCESS before the new process is
    actually serving, so only the served sha proves a deployment is live (CI-6).
    """
    return {
        "status": "healthy",
        "commit": settings.railway_git_commit_sha,
        "rbac_enabled": settings.rbac_enabled,
        "deepsearch_receipt_receiver_configured": bool(
            settings.effective_deepsearch_service_secret
        ),
        "reconciler": reconciler_health(),
    }


@router.get("/health/db")
async def db_health_check(db: Session = Depends(get_db)):
    """Database connectivity check."""
    try:
        # Simple query to verify DB connection
        result = db.execute(text("SELECT 1"))
        result.fetchone()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"Database connection failed: {str(e)}"
        ) from e


@router.get("/health/qdrant")
async def qdrant_health_check():
    """Qdrant vector database connectivity check.

    Returns health status including:
    - status: healthy/unhealthy
    - prewarmed: whether startup pre-warm succeeded
    - collections_count: number of collections in Qdrant
    - collections: list of collection names
    """
    health = get_qdrant_health()

    if health["status"] == "unhealthy":
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "prewarmed": health.get("prewarmed", False),
                "error": health.get("error", "Unknown error"),
            },
        )

    return health


@router.get("/health/ready")
async def readiness_check(db: Session = Depends(get_db)):
    """Full readiness check - verifies all services are ready.

    This endpoint should be used by load balancers to determine
    if the application is ready to receive traffic. It checks:
    - Database connectivity
    - Qdrant connectivity and pre-warm status
    """
    errors = []

    # Check database
    try:
        result = db.execute(text("SELECT 1"))
        result.fetchone()
        db_status = "healthy"
    except Exception as e:
        db_status = "unhealthy"
        errors.append(f"Database: {str(e)}")

    # Check Qdrant
    qdrant_health = get_qdrant_health()
    qdrant_status = qdrant_health["status"]
    if qdrant_status == "unhealthy":
        errors.append(f"Qdrant: {qdrant_health.get('error', 'Unknown error')}")

    # Overall status
    if errors:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "database": db_status,
                "qdrant": qdrant_status,
                "qdrant_prewarmed": is_qdrant_ready(),
                "errors": errors,
            },
        )

    return {
        "status": "ready",
        "database": db_status,
        "qdrant": qdrant_status,
        "qdrant_prewarmed": is_qdrant_ready(),
    }
