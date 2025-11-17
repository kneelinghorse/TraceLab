"""Quality scoring utilities powering PEDR-aware hybrid search."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import Document
from app.models.mission import Mission
from app.models.project import Project

MetadataLoader = Callable[[Sequence[str]], Dict[str, Dict[str, Any]]]


@dataclass(frozen=True)
class QualityFilters:
    """Normalized governance filters accepted by the scoring service."""

    min_quality_gates: Optional[int] = None
    statuses: tuple[str, ...] = field(default_factory=tuple)
    allow_pii: Optional[bool] = None


@dataclass(frozen=True)
class QualityScore:
    """Structured representation of a mission's quality metadata."""

    mission_id: Optional[str]
    status: str
    passed_gates: int
    total_gates: int
    base_score: float
    boost: float
    validated: bool
    pii_flagged: bool
    final_score: float


class QualityScoringService:
    """Derive quality multipliers from Mission Protocol gates + governance signals."""

    EXPECTED_GATES: tuple[str, ...] = (
        "research_statement",
        "evidence_links",
        "synthesis_quality",
        "traceability",
        "contradictions_resolved",
    )
    STATUS_BOOSTS: Dict[str, float] = {
        "complete": 0.20,
        "review": 0.10,
        "in_progress": 0.05,
        "draft": 0.0,
    }
    VALIDATION_BOOST: float = 0.05
    DEFAULT_BASE_SCORE: float = 0.60
    MIN_SCORE: float = 0.10
    MAX_SCORE: float = 1.50

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        metadata_loader: Optional[MetadataLoader] = None,
    ) -> None:
        self.session_factory = session_factory
        self._metadata_loader = metadata_loader

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def apply(
        self,
        results: Sequence[Dict[str, Any]],
        *,
        filters: Optional[QualityFilters] = None,
    ) -> List[Dict[str, Any]]:
        """Annotate + filter ranked chunks with PEDR quality metadata."""
        if not results:
            return []

        document_ids = self._collect_document_ids(results)
        metadata_map = self._resolve_metadata(document_ids)
        min_gates = self._normalized_min_gates(filters)
        status_filters = self._normalized_statuses(filters)
        allow_pii = filters.allow_pii if filters else None

        annotated: List[Dict[str, Any]] = []
        for entry in results:
            doc_id = self._normalize_document_id(entry.get("document_id"))
            score = self._score_metadata(metadata_map.get(doc_id))

            if min_gates is not None and score.passed_gates < min_gates:
                continue
            if status_filters and score.status.lower() not in status_filters:
                continue
            if allow_pii is False and score.pii_flagged:
                continue

            payload = dict(entry)
            payload["quality_score"] = score.final_score
            payload["quality_base_score"] = score.base_score
            payload["quality_boost"] = score.boost
            payload["quality_status"] = score.status
            payload["quality_gates_passed"] = score.passed_gates
            payload["quality_gates_total"] = score.total_gates
            payload["quality_validated"] = score.validated
            payload["quality_mission_id"] = score.mission_id
            payload["quality_pii_flagged"] = score.pii_flagged

            base_combined = float(payload.get("combined_score") or payload.get("score") or 0.0)
            payload["combined_score"] = base_combined * score.final_score
            payload["score"] = payload["combined_score"]
            annotated.append(payload)
        return annotated

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _collect_document_ids(results: Sequence[Dict[str, Any]]) -> List[str]:
        seen: Set[str] = set()
        ordered: List[str] = []
        for item in results:
            doc_id = item.get("document_id")
            normalized = QualityScoringService._normalize_document_id(doc_id)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    @staticmethod
    def _normalize_document_id(document_id: Any) -> Optional[str]:
        if not document_id:
            return None
        return str(document_id)

    @staticmethod
    def _normalized_min_gates(filters: Optional[QualityFilters]) -> Optional[int]:
        if not filters or filters.min_quality_gates is None:
            return None
        try:
            value = int(filters.min_quality_gates)
        except (TypeError, ValueError):
            return None
        value = max(0, min(len(QualityScoringService.EXPECTED_GATES), value))
        return value

    @staticmethod
    def _normalized_statuses(filters: Optional[QualityFilters]) -> Set[str]:
        if not filters or not filters.statuses:
            return set()
        return {
            status.strip().lower()
            for status in filters.statuses
            if isinstance(status, str) and status.strip()
        }

    def _resolve_metadata(self, document_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        if not document_ids:
            return {}
        if self._metadata_loader is not None:
            return dict(self._metadata_loader(document_ids))
        return self._load_metadata_from_db(document_ids)

    def _load_metadata_from_db(self, document_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        session = self.session_factory()
        try:
            parsed_ids = self._parse_document_ids(document_ids)
            if not parsed_ids:
                return {}

            rows = (
                session.query(
                    Document.id.label("document_id"),
                    Project.mission_protocol_id.label("mission_id"),
                    Mission.status.label("mission_status"),
                    Mission.quality_gates,
                    Mission.mission_data,
                )
                .join(Project, Document.project_id == Project.id)
                .outerjoin(Mission, Project.mission_protocol_id == Mission.id)
                .filter(Document.id.in_(parsed_ids))
                .all()
            )

            mapping: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                payload = row._mapping
                mapping[str(payload["document_id"])] = {
                    "mission_id": str(payload["mission_id"]) if payload["mission_id"] else None,
                    "status": payload["mission_status"],
                    "quality_gates": payload["quality_gates"],
                    "mission_data": payload["mission_data"],
                }
            return mapping
        finally:
            session.close()

    @staticmethod
    def _parse_document_ids(document_ids: Sequence[str]) -> List[uuid.UUID]:
        parsed: List[uuid.UUID] = []
        for value in document_ids:
            try:
                parsed.append(uuid.UUID(str(value)))
            except (TypeError, ValueError, AttributeError):
                continue
        return parsed

    def _score_metadata(self, metadata: Optional[Dict[str, Any]]) -> QualityScore:
        if not metadata:
            return self._default_score()

        status = str(metadata.get("status") or "unknown").strip().lower() or "unknown"
        gates = self._extract_gates(metadata.get("quality_gates"), metadata.get("mission_data"))
        passed, validated = self._summarize_gates(gates)
        total = len(self.EXPECTED_GATES)

        if total > 0:
            base_score = max(0.0, min(1.0, passed / total))
        else:
            base_score = self.DEFAULT_BASE_SCORE

        boost = self.STATUS_BOOSTS.get(status, 0.0)
        if validated:
            boost += self.VALIDATION_BOOST
        final = max(self.MIN_SCORE, min(self.MAX_SCORE, base_score * (1.0 + boost)))

        return QualityScore(
            mission_id=metadata.get("mission_id"),
            status=status,
            passed_gates=passed,
            total_gates=total,
            base_score=round(base_score or self.DEFAULT_BASE_SCORE, 4),
            boost=round(boost, 4),
            validated=validated,
            pii_flagged=self._detect_pii(metadata.get("mission_data")),
            final_score=round(final, 4),
        )

    def _extract_gates(
        self,
        quality_gates: Optional[Dict[str, Any]],
        mission_data: Optional[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        gates: Dict[str, Dict[str, Any]] = {}
        if isinstance(quality_gates, dict):
            for name, payload in quality_gates.items():
                normalized = str(name).strip().lower()
                if normalized in self.EXPECTED_GATES:
                    gates[normalized] = dict(payload or {})

        if len(gates) == len(self.EXPECTED_GATES) or not isinstance(mission_data, dict):
            return gates

        checkpoints = mission_data.get("quality_checkpoints") or []
        if isinstance(checkpoints, Iterable):
            for checkpoint in checkpoints:
                if not isinstance(checkpoint, dict):
                    continue
                name = str(checkpoint.get("gate") or "").strip().lower()
                if not name or name not in self.EXPECTED_GATES:
                    continue
                gates.setdefault(
                    name,
                    {
                        "status": checkpoint.get("status"),
                        "validated": checkpoint.get("status") == "pass",
                    },
                )
        return gates

    def _summarize_gates(self, gates: Dict[str, Dict[str, Any]]) -> tuple[int, bool]:
        passed = 0
        validated = True
        for gate in self.EXPECTED_GATES:
            payload = gates.get(gate, {})
            status = str(payload.get("status") or "").strip().lower()
            if status in {"pass", "passed", "complete"}:
                passed += 1
            validated = validated and bool(payload.get("validated"))
        return passed, validated if gates else False

    @staticmethod
    def _detect_pii(mission_data: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(mission_data, dict):
            return False

        governance = mission_data.get("governance")
        if isinstance(governance, dict):
            for key in ("pii", "pii_flag", "pii_handling", "piihandling", "piiHandling"):
                if governance.get(key) is not None:
                    return bool(governance[key])

        for key in ("pii", "pii_flag", "pii_handling", "piiHandling"):
            if mission_data.get(key) is not None:
                return bool(mission_data[key])

        tags = mission_data.get("tags")
        if isinstance(tags, Iterable):
            for tag in tags:
                if isinstance(tag, str) and tag.strip().lower() in {"pii", "privacy", "redaction"}:
                    return True
        return False

    def _default_score(self) -> QualityScore:
        return QualityScore(
            mission_id=None,
            status="unknown",
            passed_gates=0,
            total_gates=len(self.EXPECTED_GATES),
            base_score=self.DEFAULT_BASE_SCORE,
            boost=0.0,
            validated=False,
            pii_flagged=False,
            final_score=self.DEFAULT_BASE_SCORE,
        )


_QUALITY_SCORING_SERVICE: Optional[QualityScoringService] = None


def get_quality_scoring_service() -> QualityScoringService:
    """Return a singleton quality scoring service instance."""
    global _QUALITY_SCORING_SERVICE
    if _QUALITY_SCORING_SERVICE is None:
        _QUALITY_SCORING_SERVICE = QualityScoringService()
    return _QUALITY_SCORING_SERVICE


__all__ = [
    "MetadataLoader",
    "QualityFilters",
    "QualityScore",
    "QualityScoringService",
    "get_quality_scoring_service",
]
