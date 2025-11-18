"""Similarity-based evidence auto-linking for DeepSearch ingestion."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.mission_protocol import MissionProtocolComplete

_WHITESPACE = re.compile(r"\s+")


@dataclass(slots=True)
class EvidenceAutoLinkingResult:
    """Summary returned after attempting evidence-to-chunk matching."""

    attempted: int = 0
    linked: int = 0
    skipped: int = 0
    threshold: float = 0.7
    matches: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Return the ratio of linked items relative to attempted ones."""
        if self.attempted <= 0:
            return 0.0
        return round(self.linked / self.attempted, 3)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "attempted": self.attempted,
            "linked": self.linked,
            "skipped": self.skipped,
            "threshold": self.threshold,
            "success_rate": self.success_rate,
            "matches": list(self.matches),
        }


class EvidenceAutoLinkingService:
    """Match DeepSearch evidence to stored chunks using fuzzy similarity."""

    def __init__(
        self,
        *,
        similarity_threshold: float = 0.7,
        candidate_limit: int = 750,
        telemetry_path: Path | None = None,
    ) -> None:
        self.similarity_threshold = similarity_threshold
        self.candidate_limit = max(10, candidate_limit)
        repo_root = Path(__file__).resolve().parents[2]
        default_path = repo_root / "cmos" / "telemetry" / "events" / "sprint-10-deepsearch-ingestion.jsonl"
        self.telemetry_path = telemetry_path or default_path

    def link_evidence(
        self,
        db: Session,
        mission: MissionProtocolComplete,
        *,
        project_id: UUID | None = None,
        similarity_threshold: Optional[float] = None,
    ) -> EvidenceAutoLinkingResult:
        """Populate chunk identifiers for evidence rows lacking traceability."""

        evidence_items = mission.evidence or []
        result = EvidenceAutoLinkingResult(threshold=similarity_threshold or self.similarity_threshold)
        if not evidence_items:
            return result

        candidates = self._load_candidates(db, project_id)
        if not candidates:
            return result

        threshold = max(min(result.threshold, 1.0), 0.0)
        for item in evidence_items:
            if (item.chunk_id or "").strip():
                result.skipped += 1
                continue

            result.attempted += 1
            summary = self._normalize_text(item.summary)
            best = self._best_candidate(summary, candidates)
            match_payload = {
                "evidence_id": item.evidence_id,
                "chunk_id": None,
                "similarity": 0.0,
                "summary_preview": self._preview(item.summary),
            }

            if best:
                chunk_id, score = best
                match_payload["similarity"] = round(score, 3)
                if score >= threshold:
                    chunk_str = str(chunk_id)
                    item.chunk_id = chunk_str
                    item.relevance_score = round(score, 3)
                    match_payload["chunk_id"] = chunk_str
                    result.linked += 1

            result.matches.append(match_payload)

        self._log_telemetry(mission, project_id, result)
        return result

    def _load_candidates(
        self,
        db: Session,
        project_id: UUID | None,
    ) -> Sequence[Tuple[UUID, str]]:
        query = (
            db.query(DocumentChunk.id, DocumentChunk.content)
            .join(Document, Document.id == DocumentChunk.document_id)
        )
        if project_id:
            query = query.filter(Document.project_id == project_id)
        rows = (
            query.order_by(DocumentChunk.created_at.desc())
            .limit(self.candidate_limit)
            .all()
        )
        return [(row[0], row[1] or "") for row in rows if row[1]]

    def _best_candidate(
        self,
        summary: str,
        candidates: Sequence[Tuple[UUID, str]],
    ) -> Optional[Tuple[UUID, float]]:
        if not summary:
            return None

        best: Tuple[UUID, float] | None = None
        for chunk_id, content in candidates:
            normalized = self._normalize_text(content)
            if not normalized:
                continue
            score = SequenceMatcher(None, summary, normalized).ratio()
            if best is None or score > best[1]:
                best = (chunk_id, score)
        return best

    def _log_telemetry(
        self,
        mission: MissionProtocolComplete,
        project_id: UUID | None,
        result: EvidenceAutoLinkingResult,
    ) -> None:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "mission_id": mission.mission_id,
            "project_id": str(project_id) if project_id else None,
            "auto_linking": result.as_dict(),
        }
        self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        with self.telemetry_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    @staticmethod
    def _normalize_text(text: Optional[str]) -> str:
        if not text:
            return ""
        return _WHITESPACE.sub(" ", text.lower()).strip()

    @staticmethod
    def _preview(text: Optional[str], limit: int = 120) -> str:
        if not text:
            return ""
        normalized = _WHITESPACE.sub(" ", text).strip()
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3] + "..."
