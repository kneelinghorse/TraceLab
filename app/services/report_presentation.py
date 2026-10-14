"""Resolve report origin labels in batches under the caller's current read scope."""

from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.models.collection import Collection
from app.models.evidence_ledger import LedgerEntry, LedgerNote
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report
from app.services.evidence_ledger import evidence_access_filter
from app.services.evidence_scope import evidence_href, readable_evidence, scoped_query


def report_notes(db: Session, user: AuthenticatedUser, reports: list[Report]) -> dict:
    """Resolve working-note provenance through the same child and project gates as the ledger."""
    projects = scoped_query(db, user, Project).filter(Project.deleted_at.is_(None)).with_entities(Project.id)
    notes = db.query(LedgerNote).filter(
        LedgerNote.id.in_([s.source_id for r in reports for s in r.sources if s.source_type == "ledger_note"]),
        LedgerNote.project_id.in_(projects.statement),
    )
    scope = evidence_access_filter(user, LedgerNote, db)
    if scope is not None:
        notes = notes.filter(scope)
    return {note.id: note for note in notes.all()}


def report_labels(db: Session, user: AuthenticatedUser, reports: list[Report]) -> dict:
    """Never use a report's joined project or source relationship as a read grant."""
    projects = {p.id: p for p in scoped_query(db, user, Project).filter(
        Project.id.in_([r.project_id for r in reports]), Project.deleted_at.is_(None),
    ).all()}
    missions = {m.result_report_id: m for m in scoped_query(db, user, Mission).filter(
        Mission.result_report_id.in_([r.id for r in reports if r.origin == "mission"]),
    ).order_by(Mission.id).all()}
    collections = {c.id: c for c in scoped_query(db, user, Collection).filter(
        Collection.id.in_([s.source_id for r in reports for s in r.sources if s.source_type == "collection"]),
    ).all()}
    entries = {e.id: e for e in readable_evidence(db, user).filter(LedgerEntry.id.in_(
        [s.source_id for r in reports if r.origin == "agent_brief" for s in r.sources if s.source_type == "ledger_entry"]
    )).all()}
    notes = report_notes(db, user, [r for r in reports if r.origin == "agent_brief"])
    labels = {}
    for report in reports:
        project = projects.get(report.project_id)
        href = None
        if report.origin == "mission":
            mission = missions.get(report.id)
            label = f"Results of mission {mission.title}" if mission else "Mission results"
            href = f"/missions/{mission.id}?tab=results" if mission else None
        elif report.origin == "librarian":
            label = f"Written by the Librarian from {project.name}" if project else "Written by the Librarian"
            href = f"/projects/{project.id}" if project else None
        elif report.origin == "agent_brief":
            label = "Evidence brief from an agent's research session"
            entry = next((entries[s.source_id] for s in report.sources
                          if s.source_type == "ledger_entry" and s.source_id in entries), None)
            href = evidence_href(entry.project_id, entry.mission_id, entry.session_key) if entry else None
            if entry is None:
                note = next((notes[s.source_id] for s in report.sources
                             if s.source_type == "ledger_note" and s.source_id in notes), None)
                href = evidence_href(note.project_id, session_key=note.session_key) if note else None
        else:
            collection = next((collections[s.source_id] for s in report.sources
                               if s.source_type == "collection" and s.source_id in collections), None)
            label = f"Written from collection {collection.name}" if collection else f"Written from {report.chunk_count} {'excerpt' if report.chunk_count == 1 else 'excerpts'}"
            href = f"/collections/{collection.id}" if collection else None
        labels[report.id] = {"origin": report.origin, "origin_label": label, "origin_href": href,
                             "project_name": project.name if project else None}
    return labels
