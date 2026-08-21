"""Project-scope regressions for the facet aggregation boundary."""

from __future__ import annotations

import asyncio
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import event

from app.api.v1 import facets as facets_api
from app.core.config import settings
from app.core.database import engine
from app.core.security import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_SERVICE,
    AuthenticatedUser,
)
from app.models.document import Document
from app.models.project import Project
from app.models.space_member import SpaceMember
from app.models.tag import DocumentTag, Tag
from app.models.user import User
from app.models.workspace import Workspace
from app.services.faceted_search import FacetedSearchService, FacetFilters

_PASSWORD_HASH = "not-a-real-password-hash"  # noqa: S105


def _principal(user: User) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )


def _user(db_session, *, email: str, role: str = ROLE_MEMBER) -> User:
    user = User(
        email=email,
        display_name=email.split("@", maxsplit=1)[0],
        password_hash=_PASSWORD_HASH,
        role=role,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _seed_tenant_corpus(db_session):
    caller = _user(db_session, email="facet-member@example.com")
    outsider = _user(db_session, email="facet-outsider@example.com")
    shared_space = Workspace(name="Facet Shared Space")
    foreign_space = Workspace(name="Facet Foreign Space")
    db_session.add_all([shared_space, foreign_space])
    db_session.flush()
    db_session.add(
        SpaceMember(
            workspace_id=shared_space.id,
            user_id=caller.id,
            role=ROLE_MEMBER,
        )
    )
    shared_project = Project(
        name="Shared Facet Project",
        owner_id=outsider.id,
        workspace_id=shared_space.id,
    )
    foreign_project = Project(
        name="Foreign Facet Project",
        owner_id=outsider.id,
        workspace_id=foreign_space.id,
    )
    db_session.add_all([shared_project, foreign_project])
    db_session.flush()

    shared_documents = [
        Document(
            project_id=shared_project.id,
            name="Shared interview one",
            file_type="transcript",
            source_type="interview",
            collection_date=date(2025, 1, 5),
        ),
        Document(
            project_id=shared_project.id,
            name="Shared interview two",
            file_type="transcript",
            source_type="interview",
            collection_date=date(2025, 2, 10),
        ),
    ]
    foreign_documents = [
        Document(
            project_id=foreign_project.id,
            name="Foreign interview one",
            file_type="transcript",
            source_type="interview",
            collection_date=date(2024, 1, 1),
        ),
        Document(
            project_id=foreign_project.id,
            name="Foreign report",
            file_type="report",
            source_type="analysis",
            collection_date=date(2026, 1, 1),
        ),
    ]
    deleted_shared_document = Document(
        project_id=shared_project.id,
        name="Deleted shared report",
        file_type="report",
        source_type="analysis",
        collection_date=date(2027, 1, 1),
    )
    deleted_shared_document.soft_delete("facet-scope-test")
    db_session.add_all(
        [*shared_documents, *foreign_documents, deleted_shared_document]
    )
    db_session.flush()

    shared_tag = Tag(name="shared-only")
    foreign_tag = Tag(name="foreign-only")
    deleted_tag = Tag(name="deleted-only")
    db_session.add_all([shared_tag, foreign_tag, deleted_tag])
    db_session.flush()
    db_session.add_all(
        [
            *[
                DocumentTag(document_id=document.id, tag_id=shared_tag.id)
                for document in shared_documents
            ],
            *[
                DocumentTag(document_id=document.id, tag_id=foreign_tag.id)
                for document in foreign_documents
            ],
            DocumentTag(
                document_id=deleted_shared_document.id,
                tag_id=deleted_tag.id,
            ),
        ]
    )
    db_session.commit()
    return caller, shared_project, foreign_project


class _RecordingFacetService:
    def __init__(self) -> None:
        self.calls = []

    def get_facets(self, filters, allowed_project_ids=None):
        self.calls.append((filters, allowed_project_ids))
        return {
            "projects": [],
            "document_types": [],
            "source_types": [],
            "tags": [],
            "date_range": {"min": None, "max": None},
        }


def test_route_resolves_request_scope_once_and_passes_it_to_service(monkeypatch):
    """The route computes one request-local scope and does not store it globally."""
    allowed_project_ids = [uuid4(), uuid4()]
    principal = AuthenticatedUser(
        user_id=uuid4(),
        email="facet-caller@example.com",
        display_name="facet-caller",
        role=ROLE_MEMBER,
    )
    request_db = object()
    resolution_calls = []
    service = _RecordingFacetService()

    def _resolve(user, db):
        resolution_calls.append((user, db))
        return allowed_project_ids

    monkeypatch.setattr(facets_api, "accessible_project_ids", _resolve)
    monkeypatch.setattr(facets_api, "FacetedSearchService", lambda: service)

    response = asyncio.run(
        facets_api.fetch_facets(
            facets_api.FacetRequest(),
            db=request_db,
            current_user=principal,
        )
    )

    assert response.projects == []
    assert resolution_calls == [(principal, request_db)]
    assert len(service.calls) == 1
    assert service.calls[0][1] == allowed_project_ids


@pytest.mark.parametrize(
    ("rbac_enabled", "role"),
    [(True, ROLE_ADMIN), (False, ROLE_SERVICE)],
)
def test_route_privileged_and_flag_off_scopes_preserve_unrestricted_path(
    monkeypatch, rbac_enabled, role
):
    """Privileged and RBAC-off callers pass None without querying scope grants."""

    class _ExplodingDB:
        def query(self, *_args, **_kwargs):
            raise AssertionError("unrestricted facet scope queried grants")

    monkeypatch.setattr(settings, "rbac_enabled", rbac_enabled)
    service = _RecordingFacetService()
    monkeypatch.setattr(facets_api, "FacetedSearchService", lambda: service)
    principal = AuthenticatedUser(
        user_id=uuid4(),
        email="facet-unrestricted@example.com",
        display_name="facet-unrestricted",
        role=role,
    )

    asyncio.run(
        facets_api.fetch_facets(
            facets_api.FacetRequest(),
            db=_ExplodingDB(),
            current_user=principal,
        )
    )

    assert service.calls[0][1] is None


def test_route_service_principal_passes_an_explicit_empty_scope(monkeypatch):
    """A machine identity receives [] so the facet service can fail closed."""

    class _ExplodingDB:
        def query(self, *_args, **_kwargs):
            raise AssertionError("service facet scope queried human grants")

    monkeypatch.setattr(settings, "rbac_enabled", True)
    service = _RecordingFacetService()
    monkeypatch.setattr(facets_api, "FacetedSearchService", lambda: service)
    principal = AuthenticatedUser(
        user_id=uuid4(),
        email="facet-service@example.com",
        display_name="facet-service",
        role=ROLE_SERVICE,
    )

    asyncio.run(
        facets_api.fetch_facets(
            facets_api.FacetRequest(),
            db=_ExplodingDB(),
            current_user=principal,
        )
    )

    assert service.calls[0][1] == []


def test_member_space_facets_exclude_foreign_values_and_counts(monkeypatch, db_session):
    """Space membership exposes only that Space's values, counts, and date range."""
    monkeypatch.setattr(settings, "rbac_enabled", True)
    caller, shared_project, _ = _seed_tenant_corpus(db_session)

    response = asyncio.run(
        facets_api.fetch_facets(
            facets_api.FacetRequest(),
            db=db_session,
            current_user=_principal(caller),
        )
    )

    assert [item.model_dump() for item in response.projects] == [
        {
            "value": str(shared_project.id),
            "label": shared_project.name,
            "count": 2,
        }
    ]
    assert [item.model_dump() for item in response.document_types] == [
        {"value": "transcript", "label": "transcript", "count": 2}
    ]
    assert [item.model_dump() for item in response.source_types] == [
        {"value": "interview", "label": "interview", "count": 2}
    ]
    assert [item.model_dump() for item in response.tags] == [
        {"value": "shared-only", "label": "shared-only", "count": 2}
    ]
    assert response.date_range.min == date(2025, 1, 5)
    assert response.date_range.max == date(2025, 2, 10)


def test_empty_scope_returns_empty_facets_without_opening_a_session():
    """No grants fail closed before any global aggregate can execute."""

    def _explode():
        raise AssertionError("empty facet scope opened a database session")

    service = FacetedSearchService(session_factory=_explode)

    assert service.get_facets(
        FacetFilters(), allowed_project_ids=[]
    ) == {
        "projects": [],
        "document_types": [],
        "source_types": [],
        "tags": [],
        "date_range": {"min": None, "max": None},
    }


def test_none_scope_adds_no_condition_and_matches_legacy_results(db_session):
    """None is the legacy sentinel: no scope SQL and byte-identical facet data."""
    _, _, _ = _seed_tenant_corpus(db_session)
    service = FacetedSearchService()
    filters = FacetFilters()

    assert service._build_document_conditions(filters) == []
    assert service._build_document_conditions(
        filters, allowed_project_ids=None
    ) == []
    assert service.get_facets(filters, allowed_project_ids=None) == service.get_facets(
        filters
    )


def test_scope_predicate_reaches_every_aggregate_and_intersects_project_filter(
    db_session,
):
    """Every aggregate shares the allow-list predicate; explicit scope only narrows."""
    _, shared_project, foreign_project = _seed_tenant_corpus(db_session)
    shared_project_id = shared_project.id
    shared_project_name = shared_project.name
    foreign_project_id = foreign_project.id
    statements = []

    def _capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        service = FacetedSearchService()
        scoped = service.get_facets(
            FacetFilters(), allowed_project_ids=[shared_project_id]
        )
        disjoint = service.get_facets(
            FacetFilters.from_kwargs(project_id=str(foreign_project_id)),
            allowed_project_ids=[shared_project_id],
        )
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    aggregate_statements = [
        statement for statement in statements if statement.lstrip().startswith("select")
    ]
    assert len(aggregate_statements) == 10
    assert all("documents.project_id in" in statement for statement in aggregate_statements)
    assert all(
        "documents.deleted_at is null" in statement
        for statement in aggregate_statements
    )
    assert scoped["projects"] == [
        {
            "value": str(shared_project_id),
            "label": shared_project_name,
            "count": 2,
        }
    ]
    assert disjoint == {
        "projects": [],
        "document_types": [],
        "source_types": [],
        "tags": [],
        "date_range": {"min": None, "max": None},
    }
