"""Count and page readable object names without hydrating their content."""

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.authorization import accessible_filter
from app.core.security import AuthenticatedUser
from app.models.collection import Collection
from app.models.document import Document
from app.models.evidence_ledger import LedgerEntry
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report
from app.schemas.navigation_search import (
    NavigationEntityType,
    NavigationGroup,
    NavigationItem,
    NavigationSearchResponse,
)

_ENTITIES: tuple[tuple[NavigationEntityType, type[Any], Any, str], ...] = (
    ("project", Project, Project.name, "/projects"),
    ("document", Document, Document.name, "/documents"),
    ("mission", Mission, Mission.title, "/missions"),
    ("report", Report, Report.title, "/reports"),
    ("collection", Collection, Collection.name, "/collections"),
    ("evidence", LedgerEntry, LedgerEntry.claim, "/evidence"),
)


class SQLAlchemyNavigationSearchRepository:
    def search(
        self, db: Session, user: AuthenticatedUser, *, query: str,
        entity_type: NavigationEntityType | None, page: int, page_size: int,
    ) -> NavigationSearchResponse:
        groups = []
        for kind, model, title, route in _ENTITIES:
            if entity_type is not None and kind != entity_type:
                continue
            # Select scalar columns only: Collection and LedgerEntry otherwise
            # eagerly load children/source records the palette never displays.
            rows = db.query(model.id, title.label("title"))
            scope = accessible_filter(user, model, db)
            if kind == "evidence":
                # Match evidence detail: child policy OR project ownership,
                # followed by its independent readable, non-deleted parent gate.
                if scope is not None:
                    scope = or_(scope, LedgerEntry.project_id.in_(
                        select(Project.id).where(Project.owner_id == user.user_id)
                    ))
                parents = select(Project.id).where(Project.deleted_at.is_(None))
                parent_scope = accessible_filter(user, Project, db)
                if parent_scope is not None:
                    parents = parents.where(parent_scope)
                rows = rows.filter(LedgerEntry.project_id.in_(parents))
            if scope is not None:
                rows = rows.filter(scope)
            if model in (Project, Document):
                rows = rows.filter(model.deleted_at.is_(None))
            # Literal substring matching: '%' and '_' are names, not wildcards.
            rows = rows.filter(title.icontains(query, autoescape=True))
            total = rows.count()
            page_rows = rows.order_by(func.lower(title), model.id).offset((page - 1) * page_size).limit(page_size).all()
            groups.append(NavigationGroup(
                entity_type=kind, total=total, page=page, page_size=page_size,
                items=[NavigationItem(id=row.id, title=row.title, href=f"{route}/{row.id}") for row in page_rows],
            ))
        return NavigationSearchResponse(query=query, groups=groups)
