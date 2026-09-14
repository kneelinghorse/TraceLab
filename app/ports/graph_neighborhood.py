"""Persistence boundary for a caller's live relationship neighborhood."""

from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.schemas.graph_neighborhood import GraphNeighborhoodResponse
from app.schemas.navigation_search import NavigationEntityType


class GraphRootError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class GraphNeighborhoodRepository(Protocol):
    def neighborhood(
        self, db: Session, user: AuthenticatedUser, *, root_type: NavigationEntityType,
        root_id: UUID, depth: int, per_relation_limit: int, max_nodes: int,
    ) -> GraphNeighborhoodResponse: ...
