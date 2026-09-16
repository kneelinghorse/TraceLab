"""Human-authenticated, uncached relational graph reads."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.authorization import accessible_project_ids
from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.dependencies import get_graph_neighborhood_repository
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.graph_edge import GraphEdge
from app.ports.graph_neighborhood import GraphNeighborhoodRepository, GraphRootError
from app.schemas.graph_neighborhood import GraphNeighborhoodResponse
from app.schemas.navigation_search import NavigationEntityType

router = APIRouter()


@router.get("/neighborhood", response_model=GraphNeighborhoodResponse)
def get_neighborhood(
    response: Response,
    root_type: NavigationEntityType,
    root_id: UUID,
    depth: Annotated[int, Query(ge=1, le=2)] = 1,
    per_relation_limit: Annotated[int, Query(ge=1, le=50)] = 12,
    max_nodes: Annotated[int, Query(ge=1, le=150)] = 60,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    repository: GraphNeighborhoodRepository = Depends(get_graph_neighborhood_repository),
) -> GraphNeighborhoodResponse:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return repository.neighborhood(
            db, user, root_type=root_type, root_id=root_id, depth=depth,
            per_relation_limit=per_relation_limit, max_nodes=max_nodes,
        )
    except GraphRootError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail, headers={"Cache-Control": "private, no-store"}) from exc


@router.get("/stats")
def graph_stats(
    response: Response,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> dict:
    """Corpus counts for the caller's own projects.

    This route used to live on the PUBLIC health router, so it served corpus-wide
    document and chunk counts to anyone who asked, with no credentials at all. It is
    here now because this router carries require_authenticated_user; keeping an
    authorized route beside /health is what hid the hole in the first place (SEC-3).

    ``edge_counts`` is corpus-wide and cannot be scoped: graph_edges stores only URNs
    and has no project column, so there is no cheap way to attribute an edge to a
    project. Rather than disclose a global total to a restricted caller, an unprivileged
    caller gets no edge counts. Callers with unrestricted access still see them.
    """
    response.headers["Cache-Control"] = "private, no-store"
    scope = accessible_project_ids(user, db)

    documents = select(func.count()).select_from(Document).where(Document.deleted_at.is_(None))
    chunks = (
        select(func.count())
        .select_from(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.deleted_at.is_(None))
    )
    if scope is not None:
        documents = documents.where(Document.project_id.in_(scope))
        chunks = chunks.where(Document.project_id.in_(scope))

    edge_counts: dict[str, int] = {}
    if scope is None:
        edge_counts = {
            row[0]: row[1]
            for row in db.execute(
                select(GraphEdge.edge_type, func.count())
                .group_by(GraphEdge.edge_type)
                .order_by(func.count().desc())
            ).all()
        }

    return {
        "edge_counts": edge_counts,
        "total_edges": sum(edge_counts.values()),
        "document_count": int(db.execute(documents).scalar() or 0),
        "chunk_count": int(db.execute(chunks).scalar() or 0),
    }
