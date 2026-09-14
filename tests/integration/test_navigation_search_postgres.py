"""Real PostgreSQL name matching must preserve scoped counts and page reachability."""

from uuid import uuid4

import pytest

from app.adapters.repositories.sqlalchemy_navigation_search_repo import SQLAlchemyNavigationSearchRepository
from app.core.config import settings
from app.core.security import AuthenticatedUser
from app.models.collection import Collection
from app.models.evidence_ledger import LedgerEntry, LedgerSource
from app.models.project import Project
from app.models.user import User

pytestmark = pytest.mark.integration
_HASH = "placeholder-not-a-real-hash"


def test_postgres_literal_name_search_full_counts_and_evidence_parent_gate(db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user = User(email=f"{uuid4()}@example.test", display_name="Palette reader", password_hash=_HASH, role="member")
    other = User(email=f"{uuid4()}@example.test", display_name="Other reader", password_hash=_HASH, role="member")
    db_session.add_all([user, other])
    db_session.flush()
    title = f"Palette {uuid4().hex} %_"
    rows = [Collection(name=f"{title} {index:03}", owner_id=user.id) for index in range(117)]
    db_session.add_all([*rows, Collection(name=f"{title} 000 hidden", owner_id=other.id)])
    visible, private = Project(name="Owned parent", owner_id=user.id), Project(name="Private parent", owner_id=other.id)
    db_session.add_all([visible, private])
    db_session.flush()
    entries = []
    for parent, owner in ((visible, other.id), (private, user.id)):
        source = LedgerSource(project_id=parent.id, source_url="https://example.test/name", source_url_hash=uuid4().hex * 2)
        db_session.add(source)
        db_session.flush()
        entry = LedgerEntry(project_id=parent.id, owner_id=owner, claim=title, source_id=source.id, source_url=source.source_url, session_key="palette-postgres", disposition="supporting")
        db_session.add(entry)
        entries.append(entry)
    db_session.commit()
    principal = AuthenticatedUser(user_id=user.id, email=user.email, display_name=user.display_name, role=user.role)
    repository = SQLAlchemyNavigationSearchRepository()
    seen = []
    for page in range(1, 4):
        result = repository.search(db_session, principal, query=title.lower(), entity_type="collection", page=page, page_size=50)
        group = result.groups[0]
        assert group.total == 117
        seen.extend(item.id for item in group.items)
    assert seen == [row.id for row in rows]
    result = repository.search(db_session, principal, query=title, entity_type=None, page=1, page_size=5)
    evidence = next(group for group in result.groups if group.entity_type == "evidence")
    assert evidence.total == 1 and evidence.items[0].id == entries[0].id
    assert evidence.items[0].href == f"/evidence/{entries[0].id}"
