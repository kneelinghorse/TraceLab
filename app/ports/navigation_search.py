"""Persistence boundary for scoped object-name navigation."""

from typing import Protocol

from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.schemas.navigation_search import NavigationEntityType, NavigationSearchResponse


class NavigationSearchRepository(Protocol):
    def search(
        self, db: Session, user: AuthenticatedUser, *, query: str,
        entity_type: NavigationEntityType | None, page: int, page_size: int,
    ) -> NavigationSearchResponse: ...
