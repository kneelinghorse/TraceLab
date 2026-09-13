"""Read-only evidence filters and provenance for the operator browser."""

import re
from datetime import date, datetime, time, timedelta
from typing import Any
from typing import cast as type_cast
from uuid import UUID

from sqlalchemy import cast, exists, false, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Query, Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.authorization import accessible_filter
from app.core.security import AuthenticatedUser
from app.models.document import Document
from app.models.evidence_ledger import LedgerEntry
from app.models.mission import Mission
from app.models.report import Report, ReportSource


def readable_query(db: Session, user: AuthenticatedUser, model: type[Any]) -> Query[Any]:
    query = db.query(model)
    scope = accessible_filter(user, model, db)
    return query if scope is None else query.filter(scope)


def filter_entries(
    query: Query[Any],
    db: Session,
    *,
    tag: str | None = None,
    created_from: date | None = None,
    created_until: date | None = None,
    source_id: UUID | None = None,
    related_filter: ColumnElement[bool] | None = None,
) -> Query[Any]:
    """Apply exact tags and inclusive UTC dates before counting or paging."""
    if tag is not None:
        if db.get_bind().dialect.name == "postgresql":
            query = query.filter(cast(LedgerEntry.tags, JSONB).contains([tag]))
        else:
            tags = func.json_each(LedgerEntry.tags).table_valued("value")
            query = query.filter(exists(select(1).select_from(tags).where(tags.c.value == tag)))
    if created_from is not None:
        query = query.filter(LedgerEntry.created_at >= datetime.combine(created_from, time.min))
    if created_until is not None:
        query = query.filter(LedgerEntry.created_at < datetime.combine(created_until + timedelta(days=1), time.min))
    if source_id is not None:
        query = query.filter(LedgerEntry.source_id == source_id)
    if related_filter is not None:
        query = query.filter(related_filter)
    return query


def content_urls(content: str | None) -> set[str]:
    """Literal HTTP(S) citations only; never fetch source URLs from the server."""
    return {url.rstrip(".,;:!?") for url in re.findall(r'https?://[^\s<>"\[\]()]+', content or "")}


def report_evidence_filter(db: Session, user: AuthenticatedUser, report: Report) -> ColumnElement[bool]:
    missions = readable_query(db, user, Mission).filter(Mission.result_report_id == report.id)
    return or_(
        LedgerEntry.id.in_(
            select(ReportSource.source_id).where(
                ReportSource.report_id == report.id, ReportSource.source_type == "ledger_entry"
            )
        ),
        LedgerEntry.mission_id.in_(missions.with_entities(Mission.id).statement),
        LedgerEntry.source_url.in_(content_urls(type_cast(str | None, report.content))),
    )


def document_evidence_filter(db: Session, user: AuthenticatedUser, document: Document) -> ColumnElement[bool]:
    conditions = []
    if document.source_mission_id:
        mission = readable_query(db, user, Mission).filter(Mission.id == document.source_mission_id).first()
        if mission is not None:
            conditions.append(LedgerEntry.mission_id == mission.id)
    if document.source_report_id:
        report = readable_query(db, user, Report).filter(Report.id == document.source_report_id).first()
        if report is not None:
            conditions.append(report_evidence_filter(db, user, report))
    metadata: dict[str, Any] = document.document_metadata if isinstance(document.document_metadata, dict) else {}
    urls = {
        metadata[key]
        for key in ("source_url", "url", "original_url")
        if isinstance(metadata.get(key), str) and metadata[key].startswith(("https://", "http://"))
    }
    if urls:
        conditions.append(LedgerEntry.source_url.in_(urls))
    return or_(*conditions) if conditions else false()


def entry_links(db: Session, user: AuthenticatedUser, entry: LedgerEntry) -> list[dict[str, str]]:
    """Resolve persisted relationships with an independent access check per output."""
    links = []
    mission = (
        readable_query(db, user, Mission).filter(Mission.id == entry.mission_id).first() if entry.mission_id else None
    )
    if mission is not None:
        links.append(
            {
                "kind": "mission",
                "id": str(mission.id),
                "title": mission.title,
                "href": f"/missions/{mission.id}",
                "relationship": "Captured by this mission",
            }
        )
    report_ids = select(ReportSource.report_id).where(
        ReportSource.source_type == "ledger_entry", ReportSource.source_id == entry.id
    )
    reports = (
        readable_query(db, user, Report)
        .filter(Report.project_id == entry.project_id)
        .filter(or_(Report.id.in_(report_ids), Report.id == (mission.result_report_id if mission else None)))
    )
    for report in reports.order_by(Report.updated_at.desc(), Report.id).limit(50):
        links.append(
            {
                "kind": "report",
                "id": str(report.id),
                "title": report.title,
                "href": f"/reports/{report.id}",
                "relationship": "Recorded source or mission result",
            }
        )
    return links
