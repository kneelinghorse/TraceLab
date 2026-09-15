"""One ledger read scope shared by Home and the activity stream, so the two cannot drift apart."""

from typing import Any
from urllib.parse import urlencode

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Query, Session

from app.core.authorization import accessible_filter
from app.core.security import AuthenticatedUser
from app.models.evidence_ledger import LedgerEntry
from app.models.mission import Mission
from app.models.project import Project

EVIDENCE_GROUP_KEYS = (LedgerEntry.project_id, LedgerEntry.mission_id, LedgerEntry.session_key, LedgerEntry.origin)


def scoped_query(db: Session, user: AuthenticatedUser, model: type) -> Query[Any]:
    query: Query[Any] = db.query(model)
    scope = accessible_filter(user, model, db)
    return query.filter(scope) if scope is not None else query


def evidence_href(project_id, mission_id=None, session_key=None) -> str:
    params = {"project_id": str(project_id)}
    if mission_id:
        params["mission_id"] = str(mission_id)
    if session_key:
        params["session_key"] = session_key
    return "/evidence?" + urlencode(params)


def readable_evidence(db: Session, user: AuthenticatedUser) -> Query[Any]:
    """Ledger entries an aggregate may show or count for this caller.

    Match the ledger's project gate AND child-row policy, including its
    project-owner allow path. Row ownership alone cannot bypass the parent.
    Aggregates link into a mission-filtered ledger; never disclose a mission ID
    the caller cannot read, even if individual claims happen to be owned.
    """
    projects = scoped_query(db, user, Project).filter(Project.deleted_at.is_(None))
    missions = scoped_query(db, user, Mission)
    evidence = db.query(LedgerEntry).filter(
        LedgerEntry.project_id.in_(projects.with_entities(Project.id).statement),
    )
    evidence_scope = accessible_filter(user, LedgerEntry, db)
    if evidence_scope is not None:
        evidence = evidence.filter(
            or_(
                evidence_scope,
                LedgerEntry.project_id.in_(select(Project.id).where(Project.owner_id == user.user_id)),
            )
        )
    return evidence.filter(
        or_(
            LedgerEntry.mission_id.is_(None),
            LedgerEntry.mission_id.in_(missions.with_entities(Mission.id).statement),
        )
    )


def evidence_activity_groups(db: Session, user: AuthenticatedUser) -> Query[Any]:
    """Readable ledger writes grouped by project, mission, session and origin."""
    return (
        readable_evidence(db, user)
        .with_entities(
            *EVIDENCE_GROUP_KEYS,
            func.count(LedgerEntry.id).label("entry_count"),
            func.max(LedgerEntry.created_at).label("last_created_at"),
        )
        .group_by(*EVIDENCE_GROUP_KEYS)
    )
