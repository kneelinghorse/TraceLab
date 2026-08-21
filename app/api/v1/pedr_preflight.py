"""PEDR Pre-flight query endpoint for DeepSearch integration.

Enables agents to check for existing research before launching new missions.
Returns reuse recommendations based on similarity and quality thresholds.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.authorization import accessible_project_ids
from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.schemas.pedr_preflight import PreflightQuery, PreflightRecommendation
from app.services.pedr import PreflightService, get_preflight_service

router = APIRouter()
logger = logging.getLogger(__name__)


def get_service() -> PreflightService:
    """Dependency for preflight service injection."""
    return get_preflight_service()


@router.post(
    "/preflight",
    response_model=PreflightRecommendation,
    summary="Pre-flight research existence check",
    description=(
        "Query TraceLab before launching new research. Returns a recommendation "
        "to reuse existing research, review potential matches, or proceed with "
        "new research. Used by DeepSearch agents to prevent duplicate work."
    ),
    responses={
        200: {
            "description": "Pre-flight recommendation",
            "content": {
                "application/json": {
                    "examples": {
                        "reuse": {
                            "summary": "Recommend reusing existing research",
                            "value": {
                                "action": "reuse",
                                "summary": "High-quality match found: 'Passwordless Auth Patterns' (similarity: 92%, quality gates: 5/5). Recommend reusing existing research.",
                                "top_score": 0.92,
                                "match_count": 3,
                                "query": "passwordless authentication patterns",
                                "latency_ms": 45.2,
                                "matches": [
                                    {
                                        "mission_id": "DRM.0.5",
                                        "title": "Passwordless Auth Patterns",
                                        "objective": "Identify proven patterns for web applications",
                                        "status": "complete",
                                        "quality_gates_passed": 5,
                                        "similarity_score": 0.92,
                                    }
                                ],
                            },
                        },
                        "proceed": {
                            "summary": "No relevant matches found",
                            "value": {
                                "action": "proceed",
                                "summary": "No relevant existing research found for: 'quantum computing algorithms'...",
                                "top_score": None,
                                "match_count": 0,
                                "query": "quantum computing algorithms",
                                "latency_ms": 32.1,
                                "matches": [],
                            },
                        },
                    }
                }
            },
        },
        400: {"description": "Invalid query parameters"},
        401: {"description": "Authentication required"},
    },
)
async def preflight_query(
    request: PreflightQuery,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: PreflightService = Depends(get_service),
    x_agent_id: str | None = Header(
        default=None, description="Optional agent identifier"
    ),
) -> PreflightRecommendation:
    """Execute pre-flight query to check for existing research.

    This endpoint is designed for DeepSearch agents to query before
    launching new research missions. The response indicates whether
    to reuse existing research, review potential matches, or proceed
    with new research.

    Decision criteria:
    - **reuse**: Top match similarity >= 85%, quality gates >= 4, status = complete
    - **review**: Top match similarity >= 70%, status = complete
    - **proceed**: No relevant matches found

    The query uses hybrid search (semantic + keyword) with quality-aware
    ranking to find the most relevant existing missions.
    """
    if not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query text must not be empty.",
        )

    agent = x_agent_id or current_user.username or "unknown"
    allowed_project_ids = accessible_project_ids(current_user, db)

    try:
        result = service.query(
            request,
            agent=agent,
            allowed_project_ids=allowed_project_ids,
        )
    except Exception as e:
        logger.exception("Pre-flight query failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pre-flight query failed. Please try again.",
        ) from e

    return result
