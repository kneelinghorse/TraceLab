"""Similarity-based evidence auto-linking for DeepSearch ingestion."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.mission_protocol import MissionProtocolComplete

if TYPE_CHECKING:
    from app.services.embedding_service import EmbeddingService
    from app.services.qdrant_service import QdrantService

_WHITESPACE = re.compile(r"\s+")
logger = logging.getLogger(__name__)


class AutoLinkErrorType(str, Enum):
    """Error taxonomy for evidence auto-linking failures.

    Classifies why auto-linking failed to enable targeted retry strategies
    and observability dashboards.
    """

    NO_EMBEDDING = "no_embedding"
    """Evidence text couldn't generate embedding (empty/invalid content)."""

    LOW_SIMILARITY = "low_similarity"
    """Best match below similarity threshold (configurable, default 0.7)."""

    NO_CHUNKS = "no_chunks"
    """No chunks exist in project for matching."""

    TIMEOUT = "timeout"
    """Qdrant/embedding service timeout."""

    VALIDATION_ERROR = "validation_error"
    """Evidence structure invalid or missing required fields."""

    EMPTY_CONTENT = "empty_content"
    """Evidence summary/content is empty or whitespace-only."""

    DATABASE_ERROR = "database_error"
    """Database query failed during candidate loading."""

    EMBEDDING_FAILED = "embedding_failed"
    """Embedding service returned an error for this evidence summary."""

    QDRANT_ERROR = "qdrant_error"
    """Qdrant vector search failed (connection, timeout, etc.)."""


@dataclass(slots=True)
class EvidenceMatchResult:
    """Individual evidence matching outcome with error tracking."""

    evidence_id: str
    chunk_id: str | None = None
    similarity: float = 0.0
    summary_preview: str = ""
    success: bool = False
    error_type: AutoLinkErrorType | None = None
    retry_count: int = 0
    last_error: str | None = None


@dataclass(slots=True)
class EvidenceAutoLinkingResult:
    """Summary returned after attempting evidence-to-chunk matching."""

    attempted: int = 0
    linked: int = 0
    skipped: int = 0
    failed: int = 0
    threshold: float = 0.7
    matches: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Return the ratio of linked items relative to attempted ones."""
        if self.attempted <= 0:
            return 0.0
        return round(self.linked / self.attempted, 3)

    @property
    def failure_rate(self) -> float:
        """Return the ratio of failed items relative to attempted ones."""
        if self.attempted <= 0:
            return 0.0
        return round(self.failed / self.attempted, 3)

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "linked": self.linked,
            "skipped": self.skipped,
            "failed": self.failed,
            "threshold": self.threshold,
            "success_rate": self.success_rate,
            "failure_rate": self.failure_rate,
            "matches": list(self.matches),
            "errors": list(self.errors),
        }


class EvidenceAutoLinkingService:
    """Match DeepSearch evidence to stored chunks using embedding similarity.

    Primary path uses EmbeddingService + QdrantService for semantic cosine
    similarity. Falls back to difflib SequenceMatcher when embedding
    infrastructure is unavailable (controlled by fallback_to_difflib flag).
    """

    def __init__(
        self,
        *,
        similarity_threshold: float | None = None,
        candidate_limit: int = 750,
        telemetry_path: Path | None = None,
        embedding_service: EmbeddingService | None = None,
        qdrant_service: QdrantService | None = None,
        top_k: int | None = None,
        fallback_to_difflib: bool | None = None,
    ) -> None:
        from app.core.config import settings

        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else settings.auto_link_similarity_threshold
        )
        self.candidate_limit = max(10, candidate_limit)
        self.top_k = top_k if top_k is not None else settings.auto_link_top_k
        self.fallback_to_difflib = (
            fallback_to_difflib
            if fallback_to_difflib is not None
            else settings.auto_link_fallback_to_difflib
        )

        self._embedding_service = embedding_service
        self._qdrant_service = qdrant_service

        repo_root = Path(__file__).resolve().parents[2]
        default_path = (
            repo_root
            / "cmos"
            / "telemetry"
            / "events"
            / "sprint-10-deepsearch-ingestion.jsonl"
        )
        self.telemetry_path = telemetry_path or default_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def link_evidence(
        self,
        db: Session,
        mission: MissionProtocolComplete,
        *,
        project_id: UUID | None = None,
        similarity_threshold: float | None = None,
    ) -> EvidenceAutoLinkingResult:
        """Populate chunk identifiers for evidence rows lacking traceability."""

        evidence_items = mission.evidence or []
        threshold = similarity_threshold or self.similarity_threshold
        result = EvidenceAutoLinkingResult(threshold=threshold)
        if not evidence_items:
            return result

        threshold = max(min(result.threshold, 1.0), 0.0)

        # Strategy selection: embedding path vs difflib fallback
        embedding_svc, qdrant_svc = self._resolve_services()
        use_embeddings = embedding_svc is not None and qdrant_svc is not None

        if use_embeddings:
            return self._link_via_embeddings(
                db,
                mission,
                project_id,
                result,
                threshold,
                embedding_svc,
                qdrant_svc,
            )

        if self.fallback_to_difflib:
            logger.info("Embedding services unavailable, falling back to difflib")
            return self._link_via_difflib(db, mission, project_id, result, threshold)

        # No embedding services and fallback disabled — fail all items
        for item in evidence_items:
            if (item.chunk_id or "").strip():
                result.skipped += 1
                continue
            result.attempted += 1
            result.failed += 1
            result.errors.append(
                {
                    "evidence_id": item.evidence_id,
                    "error_type": AutoLinkErrorType.EMBEDDING_FAILED.value,
                    "message": "Embedding service unavailable and fallback disabled",
                }
            )
            result.matches.append(
                {
                    "evidence_id": item.evidence_id,
                    "chunk_id": None,
                    "similarity": 0.0,
                    "summary_preview": self._preview(item.summary),
                    "success": False,
                    "error_type": AutoLinkErrorType.EMBEDDING_FAILED.value,
                    "method": "none",
                }
            )

        self._log_telemetry(mission, project_id, result)
        return result

    # ------------------------------------------------------------------
    # Embedding path (primary)
    # ------------------------------------------------------------------

    def _link_via_embeddings(
        self,
        db: Session,
        mission: MissionProtocolComplete,
        project_id: UUID | None,
        result: EvidenceAutoLinkingResult,
        threshold: float,
        embedding_svc: EmbeddingService,
        qdrant_svc: QdrantService,
    ) -> EvidenceAutoLinkingResult:
        """Link evidence using embed + Qdrant cosine similarity search."""

        evidence_items = mission.evidence or []

        for item in evidence_items:
            if (item.chunk_id or "").strip():
                result.skipped += 1
                continue

            result.attempted += 1
            summary = (item.summary or "").strip()
            match_payload: dict[str, Any] = {
                "evidence_id": item.evidence_id,
                "chunk_id": None,
                "similarity": 0.0,
                "summary_preview": self._preview(item.summary),
                "success": False,
                "error_type": None,
                "method": "embedding",
            }

            # Empty content check
            if not summary:
                result.failed += 1
                match_payload["error_type"] = AutoLinkErrorType.EMPTY_CONTENT.value
                result.errors.append(
                    {
                        "evidence_id": item.evidence_id,
                        "error_type": AutoLinkErrorType.EMPTY_CONTENT.value,
                        "message": "Evidence summary is empty or whitespace-only",
                    }
                )
                result.matches.append(match_payload)
                continue

            # Step 1: Embed the evidence summary
            try:
                query_vector = embedding_svc.generate_embedding(summary)
            except Exception as exc:
                logger.warning("Embedding failed for %s: %s", item.evidence_id, exc)
                result.failed += 1
                match_payload["error_type"] = AutoLinkErrorType.EMBEDDING_FAILED.value
                result.errors.append(
                    {
                        "evidence_id": item.evidence_id,
                        "error_type": AutoLinkErrorType.EMBEDDING_FAILED.value,
                        "message": f"Embedding generation failed: {exc}",
                    }
                )
                result.matches.append(match_payload)
                continue

            # Step 2: Search Qdrant for nearest chunks
            try:
                hits = qdrant_svc.search_chunks(
                    query_vector=query_vector,
                    top_k=self.top_k,
                    project_id=str(project_id) if project_id else None,
                )
            except Exception as exc:
                logger.warning("Qdrant search failed for %s: %s", item.evidence_id, exc)
                result.failed += 1
                match_payload["error_type"] = AutoLinkErrorType.QDRANT_ERROR.value
                result.errors.append(
                    {
                        "evidence_id": item.evidence_id,
                        "error_type": AutoLinkErrorType.QDRANT_ERROR.value,
                        "message": f"Qdrant search failed: {exc}",
                    }
                )
                result.matches.append(match_payload)
                continue

            # Step 3: Evaluate results
            if not hits:
                result.failed += 1
                match_payload["error_type"] = AutoLinkErrorType.NO_CHUNKS.value
                result.errors.append(
                    {
                        "evidence_id": item.evidence_id,
                        "error_type": AutoLinkErrorType.NO_CHUNKS.value,
                        "message": "No chunks returned from Qdrant search",
                    }
                )
                result.matches.append(match_payload)
                continue

            best = hits[0]
            score = best["score"]
            match_payload["similarity"] = round(score, 3)

            # Log runner-up score for threshold calibration
            if len(hits) > 1:
                match_payload["runner_up_score"] = round(hits[1]["score"], 3)

            if score >= threshold:
                chunk_str = best["chunk_id"]
                item.chunk_id = chunk_str
                item.relevance_score = round(score, 3)
                match_payload["chunk_id"] = chunk_str
                match_payload["success"] = True
                result.linked += 1
            else:
                result.failed += 1
                match_payload["error_type"] = AutoLinkErrorType.LOW_SIMILARITY.value
                result.errors.append(
                    {
                        "evidence_id": item.evidence_id,
                        "error_type": AutoLinkErrorType.LOW_SIMILARITY.value,
                        "message": f"Best match ({score:.3f}) below threshold ({threshold})",
                        "best_similarity": round(score, 3),
                        "threshold": threshold,
                    }
                )

            result.matches.append(match_payload)

        self._log_telemetry(mission, project_id, result)
        return result

    # ------------------------------------------------------------------
    # Difflib fallback path (legacy)
    # ------------------------------------------------------------------

    def _link_via_difflib(
        self,
        db: Session,
        mission: MissionProtocolComplete,
        project_id: UUID | None,
        result: EvidenceAutoLinkingResult,
        threshold: float,
    ) -> EvidenceAutoLinkingResult:
        """Fallback: link evidence using difflib SequenceMatcher."""

        evidence_items = mission.evidence or []
        candidates = self._load_candidates(db, project_id)
        no_chunks = len(candidates) == 0

        for item in evidence_items:
            if (item.chunk_id or "").strip():
                result.skipped += 1
                continue

            result.attempted += 1
            summary = self._normalize_text(item.summary)
            match_payload: dict[str, Any] = {
                "evidence_id": item.evidence_id,
                "chunk_id": None,
                "similarity": 0.0,
                "summary_preview": self._preview(item.summary),
                "success": False,
                "error_type": None,
                "method": "difflib",
            }

            # Check for empty content
            if not summary:
                result.failed += 1
                match_payload["error_type"] = AutoLinkErrorType.EMPTY_CONTENT.value
                result.errors.append(
                    {
                        "evidence_id": item.evidence_id,
                        "error_type": AutoLinkErrorType.EMPTY_CONTENT.value,
                        "message": "Evidence summary is empty or whitespace-only",
                    }
                )
                result.matches.append(match_payload)
                continue

            # Check for no chunks in project
            if no_chunks:
                result.failed += 1
                match_payload["error_type"] = AutoLinkErrorType.NO_CHUNKS.value
                result.errors.append(
                    {
                        "evidence_id": item.evidence_id,
                        "error_type": AutoLinkErrorType.NO_CHUNKS.value,
                        "message": "No chunks exist in project for matching",
                    }
                )
                result.matches.append(match_payload)
                continue

            best = self._best_candidate(summary, candidates)
            if best:
                chunk_id, score = best
                match_payload["similarity"] = round(score, 3)
                if score >= threshold:
                    chunk_str = str(chunk_id)
                    item.chunk_id = chunk_str
                    item.relevance_score = round(score, 3)
                    match_payload["chunk_id"] = chunk_str
                    match_payload["success"] = True
                    result.linked += 1
                else:
                    # Below threshold - classify as LOW_SIMILARITY
                    result.failed += 1
                    match_payload["error_type"] = AutoLinkErrorType.LOW_SIMILARITY.value
                    result.errors.append(
                        {
                            "evidence_id": item.evidence_id,
                            "error_type": AutoLinkErrorType.LOW_SIMILARITY.value,
                            "message": f"Best match ({score:.3f}) below threshold ({threshold})",
                            "best_similarity": round(score, 3),
                            "threshold": threshold,
                        }
                    )
            else:
                result.failed += 1
                match_payload["error_type"] = AutoLinkErrorType.NO_EMBEDDING.value
                result.errors.append(
                    {
                        "evidence_id": item.evidence_id,
                        "error_type": AutoLinkErrorType.NO_EMBEDDING.value,
                        "message": "Could not find any matching candidate",
                    }
                )

            result.matches.append(match_payload)

        self._log_telemetry(mission, project_id, result)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_services(
        self,
    ) -> tuple[EmbeddingService | None, QdrantService | None]:
        """Lazily resolve embedding and Qdrant services from singletons."""
        embedding = self._embedding_service
        qdrant = self._qdrant_service

        if embedding is None:
            try:
                from app.services.embedding_service import get_embedding_service

                embedding = get_embedding_service()
            except Exception:
                embedding = None

        if qdrant is None:
            try:
                from app.services.qdrant_service import get_qdrant_service

                qdrant = get_qdrant_service()
            except Exception:
                qdrant = None

        return embedding, qdrant

    def _load_candidates(
        self,
        db: Session,
        project_id: UUID | None,
    ) -> Sequence[tuple[UUID, str]]:
        query = db.query(DocumentChunk.id, DocumentChunk.content).join(
            Document, Document.id == DocumentChunk.document_id
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
        candidates: Sequence[tuple[UUID, str]],
    ) -> tuple[UUID, float] | None:
        if not summary:
            return None

        best: tuple[UUID, float] | None = None
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
        methods_used = {m.get("method", "unknown") for m in result.matches}
        linking_method = "embedding" if "embedding" in methods_used else "difflib"

        payload = {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "mission_id": mission.mission_id,
            "project_id": str(project_id) if project_id else None,
            "linking_method": linking_method,
            "auto_linking": result.as_dict(),
        }
        self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        with self.telemetry_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    @staticmethod
    def _normalize_text(text: str | None) -> str:
        if not text:
            return ""
        return _WHITESPACE.sub(" ", text.lower()).strip()

    @staticmethod
    def _preview(text: str | None, limit: int = 120) -> str:
        if not text:
            return ""
        normalized = _WHITESPACE.sub(" ", text).strip()
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3] + "..."
