"""Bounded lexical evidence for human duplicate review; never writes to the corpus."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations
from uuid import UUID

from sqlalchemy import case, func
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.models.document import Document
from app.models.project import Project
from app.services.document_policy import document_read_policy
from app.services.librarian import LibrarianConflict

VERSION = "normalized-text-five-word-phrases-v1"
DOCUMENT_LIMIT = 100
CHARACTER_LIMIT = 20000
PAIR_LIMIT = 20


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _shingles(words: list[str]) -> set[tuple[str, ...]]:
    return {tuple(words[index:index + 5]) for index in range(len(words) - 4)}


@dataclass
class _Text:
    id: str
    name: str
    content: str
    normalized: str
    digest: str
    word_count: int
    shingles: set[tuple[str, ...]]
    paragraphs: list[tuple[str, set[tuple[str, ...]]]]

    def source(self) -> dict:
        return {"id": self.id, "name": self.name, "href": f"/documents/{self.id}"}


def _prepare(row: Row) -> _Text | None:
    content = row.content or ""
    normalized = _normalize(content)
    if not normalized:
        return None
    words = re.findall(r"\w+", normalized)
    paragraphs = []
    seen = set()
    for paragraph in re.split(r"\n\s*\n", content):
        clean = _normalize(paragraph)
        tokens = re.findall(r"\w+", clean)
        if len(tokens) >= 15 and clean not in seen:
            seen.add(clean)
            paragraphs.append((paragraph.strip(), _shingles(tokens)))
    return _Text(str(row.id), row.name[:160], content, normalized,
                 hashlib.sha256(content.encode()).hexdigest(), len(words), _shingles(words), paragraphs)


def _readable_query(db: Session, user: AuthenticatedUser, project_id: UUID):
    # Do not load raw bytes or an overlong text just to exclude it in Python.
    query = db.query(
        Document.id, Document.name, func.length(Document.content).label("raw_length"),
        case((func.length(Document.content) <= CHARACTER_LIMIT, Document.content), else_=None).label("content"),
    ).join(Project, Project.id == Document.project_id).filter(
        Document.project_id == project_id, Document.deleted_at.is_(None), Project.deleted_at.is_(None),
    )
    policy = document_read_policy(user, db)
    return query.filter(policy) if policy is not None else query


def _candidate(left: _Text, right: _Text) -> dict | None:
    if left.normalized == right.normalized:
        kind, score = "exact_text", 1.0
        basis = "The complete non-empty extracted texts are equal after Unicode, case and whitespace normalization."
        evidence = [{"left_excerpt": left.content[:400], "right_excerpt": right.content[:400]}]
    else:
        if min(left.word_count, right.word_count) < 60 or min(left.word_count, right.word_count) / max(left.word_count, right.word_count) < 0.8:
            return None
        common = left.shingles & right.shingles
        score = len(common) / len(left.shingles | right.shingles) if common else 0
        if len(common) < 40 or score < 0.8:
            return None
        # A single reused disclaimer must not become a duplicate suggestion,
        # even when it dominates the word count. Repeated copies count once.
        left_support = [text for text, phrases in left.paragraphs if len(phrases & common) / len(phrases) >= 0.6]
        right_support = [text for text, phrases in right.paragraphs if len(phrases & common) / len(phrases) >= 0.6]
        if min(len(left_support), len(right_support)) < 2:
            return None
        kind = "probable_overlap"
        basis = f"{score:.0%} five-word phrase overlap, with substantial shared text in at least two distinct passages in each document."
        evidence = [{"left_excerpt": a[:400], "right_excerpt": b[:400]} for a, b in zip(left_support[:2], right_support[:2], strict=False)]
    candidate_id = hashlib.sha256(json.dumps([VERSION, left.id, left.digest, right.id, right.digest]).encode()).hexdigest()
    return {"candidate_id": candidate_id, "kind": kind, "score": round(score, 4),
            "documents": [left.source(), right.source()], "basis": basis, "evidence": evidence,
            "recommendation": "Compare source dates, annotations and purpose. Keep both if either adds useful context. If one is redundant, decide which to retain before using its existing document controls. This review changes neither document."}


def scan_duplicates(db: Session, user: AuthenticatedUser, project: Project) -> dict:
    query = _readable_query(db, user, project.id)
    total = query.count()
    rows = query.order_by(Document.id).limit(DOCUMENT_LIMIT).all()
    prepared = [text for row in rows if (text := _prepare(row)) is not None]
    candidates = [pair for a, b in combinations(prepared, 2) if (pair := _candidate(a, b)) is not None]
    candidates.sort(key=lambda pair: (pair["kind"] != "exact_text", -pair["score"], [doc["id"] for doc in pair["documents"]]))
    overlong = sum((row.raw_length or 0) > CHARACTER_LIMIT for row in rows)
    return {"project_id": str(project.id), "scanned_at": datetime.now(UTC).isoformat(), "method": VERSION,
            "candidates": candidates[:PAIR_LIMIT], "coverage": {
                "readable_documents": total, "scanned_documents": len(rows), "examined_documents": len(prepared),
                "empty_documents": len(rows) - len(prepared) - overlong, "overlong_documents": overlong,
                "exact_only_documents": sum(text.word_count < 60 or len(text.paragraphs) < 2 for text in prepared),
                "limited": total > len(rows), "document_limit": DOCUMENT_LIMIT, "character_limit": CHARACTER_LIMIT,
                "candidate_count": len(candidates), "candidates_limited": len(candidates) > PAIR_LIMIT, "pair_limit": PAIR_LIMIT,
            }}


def compare_duplicates(db: Session, user: AuthenticatedUser, project: Project, document_ids: list[UUID], candidate_id: str) -> dict:
    rows = _readable_query(db, user, project.id).filter(Document.id.in_(document_ids)).order_by(Document.id).all()
    if len(rows) != 2:
        raise LookupError("These sources are no longer available in this project. Scan again.")
    left, right = (_prepare(row) for row in rows)
    if left is None or right is None:
        raise LibrarianConflict("The compared text is empty or exceeds the limit. Scan again.")
    pair = _candidate(left, right)
    if pair is None or pair["candidate_id"] != candidate_id:
        raise LibrarianConflict("The compared text changed or the comparison is invalid. Scan again.")
    return {"candidate": pair, "documents": [{**text.source(), "content": text.content} for text in (left, right)]}
