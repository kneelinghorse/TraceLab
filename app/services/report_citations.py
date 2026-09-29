"""Durable citation identities; all source details are resolved under current policy."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.authorization import accessible_filter
from app.core.authorization import accessible_project_ids as current_project_scope
from app.core.config import settings
from app.core.security import AuthenticatedUser
from app.models.chunk import DocumentChunk
from app.models.collection import Collection
from app.models.document import Document
from app.models.mission import Mission
from app.models.project import Project
from app.models.user import User
from app.schemas.librarian import AssistantReply, ReplySegment
from app.services.corpus_qa import chunk_href
from app.services.document_policy import document_read_policy
from app.services.librarian import validate_provenance

MARKER = re.compile(r"\[(\d+)\]")


def text_hash(content: str) -> str:
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()


def validate_citation_coverage(content: str, markers: set[int]) -> None:
    """Apply the Librarian's claim rule to synthesis paragraphs/list items.

    Synthesis is corpus prose, except standalone markdown headings/separators.
    A marker's presence proves identity, not that the model's claim is true.
    """
    blocks = re.split(r"\n\s*\n|\n(?=\s*(?:[-*+] |\d+\. ))", content.strip())
    claims = []
    for block in blocks:
        prose = "\n".join(
            line for line in block.splitlines()
            if not re.fullmatch(r"\s*(?:#{1,6} .+|[-*_]{3,})\s*", line)
        ).strip()
        if prose:
            claims.append(prose)
    if not claims:
        raise ValueError("Synthesis has no cited claims; citation support is required.")
    # Validate one block at a time to retain the shared validator's bounded schema.
    for claim in claims:
        labels = list(dict.fromkeys(MARKER.findall(claim)))
        if len(labels) > 20 or len(claim) > 20_000:
            raise ValueError("Synthesis citation block exceeds validation limits.")
        reply = AssistantReply(segments=[ReplySegment(
            kind="corpus_claim", text=claim, citations=labels,
        )])
        if validate_provenance(reply, [str(marker) for marker in markers]):
            raise ValueError("Synthesis citation support is missing or outside supplied text.")
    if any(int(label) not in markers for label in MARKER.findall(content)):
        raise ValueError("Synthesis citation is outside supplied text.")


def persistable_citations(
    db: Session, result: dict[str, Any], *, document_filter=None,
    accessible_project_ids: list[UUID] | None = None,
    source_user: AuthenticatedUser | None = None,
) -> list[dict[str, Any]]:
    """Recheck the generated mapping in the report transaction; never infer one."""
    if source_user is not None and settings.rbac_enabled:
        caller = db.get(User, source_user.user_id, populate_existing=True)
        if caller is None or not caller.is_active:
            raise ValueError("Report citation access is no longer available to the caller.")
        fresh_user = AuthenticatedUser(user_id=caller.id, email=caller.email, display_name=caller.display_name, role=caller.role)
        document_filter = document_read_policy(fresh_user, db)
        accessible_project_ids = current_project_scope(fresh_user, db)
    citations = result.get("citations") or []
    effective = {str(value) for value in result.get("effective_chunk_ids", [])}
    markers = {c.get("marker") for c in citations}
    if not citations or any(type(m) is not int or m < 1 for m in markers):
        raise ValueError("A report requires a validated citation mapping.")
    if len(markers) != len(citations):
        raise ValueError("Duplicate citation markers are not a valid mapping.")
    validate_citation_coverage(result["content"], markers)
    if {int(m) for m in MARKER.findall(result["content"])} != markers:
        raise ValueError("Report citation mapping differs from the reviewed content.")
    ids = [UUID(value) for value in effective]
    query = db.query(DocumentChunk, Document).join(
        Document, Document.id == DocumentChunk.document_id
    ).join(Project, Project.id == Document.project_id).filter(
        DocumentChunk.id.in_(ids), Document.deleted_at.is_(None), Project.deleted_at.is_(None),
    )
    if document_filter is not None:
        query = query.filter(document_filter)
    if accessible_project_ids is not None:
        query = query.filter(Document.project_id.in_(accessible_project_ids))
    # Prevent a concurrent source edit/deletion while the report is committed.
    rows = query.with_for_update(of=[DocumentChunk, Document, Project]).all()
    live = {str(chunk.id): (chunk, doc) for chunk, doc in rows}
    if set(live) != effective:
        raise ValueError("Report citation inputs are no longer readable.")
    manifest = []
    for citation in citations:
        identity = citation["chunk_id"]
        row = live.get(identity)
        if identity not in effective or row is None:
            raise ValueError("Report citation source is no longer readable.")
        chunk, doc = row
        if (not (chunk.content or "").strip()
                or str(doc.id) != citation.get("document_id")
                or text_hash(chunk.content) != citation.get("content_hash")):
            raise ValueError("Report citation source changed after generation.")
        manifest.append({key: citation[key] for key in (
            "marker", "chunk_id", "document_id", "content_hash",
        )})
    return manifest


def generation_provenance(result: dict[str, Any], owner_id) -> dict[str, Any]:
    return {
        "origin": "synthesis", "model": result.get("model"),
        "requested_by": str(owner_id) if owner_id else None,
        "generated_at": result.get("generated_at") or datetime.now(UTC).isoformat(),
        "cache_hit": bool(result.get("cache_hit")),
        "accepted_by": None, "accepted_at": None,
    }


def readable_citations(db: Session, user, report) -> list[dict[str, Any]]:
    manifest = getattr(report, "citation_manifest", None) or []
    if not manifest:
        return []
    query = db.query(DocumentChunk, Document).join(
        Document, Document.id == DocumentChunk.document_id
    ).join(Project, Project.id == Document.project_id).filter(
        DocumentChunk.id.in_([UUID(c["chunk_id"]) for c in manifest]),
        Document.deleted_at.is_(None), Project.deleted_at.is_(None),
    )
    policy = document_read_policy(user, db)
    if policy is not None:
        query = query.filter(policy)
    live = {str(chunk.id): (chunk, doc) for chunk, doc in query.all()}
    citations = []
    for item in manifest:
        citation = {"marker": item["marker"], "available": False}
        row = live.get(item["chunk_id"])
        if row:
            chunk, doc = row
            if str(doc.id) == item["document_id"] and text_hash(chunk.content or "") == item["content_hash"]:
                citation.update(
                    available=True, chunk_id=str(chunk.id), document_id=str(doc.id),
                    excerpt=chunk.content.strip()[:100],
                    href=chunk_href(str(doc.id), str(chunk.id), chunk.chunk_index),
                )
        citations.append(citation)
    return citations


def original_documents(db: Session, user, report) -> list[dict[str, str]]:
    """Result-document provenance is independent of claim support and report access."""
    missions = db.query(Mission).filter(Mission.result_report_id == report.id)
    scope = accessible_filter(user, Mission, db)
    if scope is not None:
        missions = missions.filter(scope)
    ids = set()
    for mission in missions.all():
        for value in mission.result_document_ids or []:
            try:
                ids.add(UUID(str(value)))
            except (TypeError, ValueError):
                continue
    if not ids:
        return []
    query = db.query(Document).join(Project, Project.id == Document.project_id).filter(
        Document.id.in_(ids), Document.deleted_at.is_(None), Project.deleted_at.is_(None),
    )
    policy = document_read_policy(user, db)
    if policy is not None:
        query = query.filter(policy)
    return [{"document_id": str(doc.id), "name": doc.name, "href": f"/documents/{doc.id}"}
            for doc in query.order_by(Document.id).all()]


def readable_source_records(db: Session, user, report) -> list:
    """Input records are provenance, but their identities still require access."""
    sources = report.sources or []
    chunk_ids = [s.source_id for s in sources if s.source_type == "chunk"]
    query = db.query(DocumentChunk.id).join(Document).join(Project).filter(
        DocumentChunk.id.in_(chunk_ids), Document.deleted_at.is_(None), Project.deleted_at.is_(None),
    )
    policy = document_read_policy(user, db)
    if policy is not None:
        query = query.filter(policy)
    readable = {str(row.id) for row in query.all()}
    collections = db.query(Collection.id).filter(Collection.id.in_(
        [s.source_id for s in sources if s.source_type == "collection"]
    ))
    scope = accessible_filter(user, Collection, db)
    if scope is not None:
        collections = collections.filter(scope)
    readable_collections = {str(row.id) for row in collections.all()}
    return [s for s in sources if (
        (s.source_type == "chunk" and str(s.source_id) in readable)
        or (s.source_type == "collection" and str(s.source_id) in readable_collections)
        or s.source_type not in {"chunk", "collection"}
    )]
