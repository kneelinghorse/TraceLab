"""Quality scoring utilities powering PEDR-aware hybrid search."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import Document
from app.models.mission import Mission
from app.models.project import Project

MetadataLoader = Callable[[Sequence[str]], Dict[str, Dict[str, Any]]]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QualityFilters:
    """Normalized governance filters accepted by the scoring service."""

    min_quality_gates: Optional[int] = None
    statuses: tuple[str, ...] = field(default_factory=tuple)
    allow_pii: Optional[bool] = None
    governance_mode: str = "strict"


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
        "complete": 0.12,
        "review": 0.09,
        "in_progress": 0.05,
        "draft": 0.0,
    }
    STATUS_CURVE_EXPONENTS: Dict[str, float] = {
        "review": 0.80,
        "in_progress": 0.70,
        "draft": 0.45,
    }
    GOVERNANCE_MODES: Set[str] = {"strict", "soft", "warn"}
    SOFT_PII_PENALTY: float = -0.30
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
        governance_mode = self._normalized_governance_mode(filters)

        annotated: List[Dict[str, Any]] = []
        warned_pii = 0
        for entry in results:
            doc_id = self._normalize_document_id(entry.get("document_id"))
            score = self._score_metadata(metadata_map.get(doc_id))

            if min_gates is not None and score.passed_gates < min_gates:
                continue
            if status_filters and score.status.lower() not in status_filters:
                continue
            governance_penalty = 0.0
            if allow_pii is False and score.pii_flagged:
                if governance_mode == "strict":
                    continue
                if governance_mode == "soft":
                    governance_penalty = self.SOFT_PII_PENALTY
                elif governance_mode == "warn":
                    warned_pii += 1

            payload = dict(entry)
            effective_score = self._apply_governance_penalty(score.final_score, governance_penalty)
            payload["quality_score"] = effective_score
            payload["quality_base_score"] = score.base_score
            payload["quality_boost"] = score.boost
            payload["quality_status"] = score.status
            payload["quality_gates_passed"] = score.passed_gates
            payload["quality_gates_total"] = score.total_gates
            payload["quality_validated"] = score.validated
            payload["quality_mission_id"] = score.mission_id
            payload["quality_pii_flagged"] = score.pii_flagged

            base_combined = float(payload.get("combined_score") or payload.get("score") or 0.0)
            payload["combined_score"] = base_combined * effective_score
            payload["score"] = payload["combined_score"]
            annotated.append(payload)
        if warned_pii:
            logger.warning(
                "Governance warn mode included %d PII-flagged results.",
                warned_pii,
            )
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

    @classmethod
    def _normalized_governance_mode(cls, filters: Optional[QualityFilters]) -> str:
        if not filters:
            return "strict"
        value = str(filters.governance_mode or "").strip().lower()
        return value if value in cls.GOVERNANCE_MODES else "strict"

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
                    Mission.mission_metadata,
                    Mission.execution_metadata,
                )
                .join(Project, Document.project_id == Project.id)
                .outerjoin(Mission, Project.mission_protocol_id == Mission.id)
                .filter(Document.id.in_(parsed_ids))
                .all()
            )

            mapping: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                payload = row._mapping
                # Extract quality gates from mission_metadata if present
                mission_meta = payload.get("mission_metadata") or {}
                mapping[str(payload["document_id"])] = {
                    "mission_id": str(payload["mission_id"]) if payload["mission_id"] else None,
                    "status": payload["mission_status"],
                    "quality_gates": mission_meta.get("quality_gates"),
                    "mission_data": payload.get("execution_metadata"),
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
        base_score = self._apply_status_curve(base_score, status)

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

    @classmethod
    def _apply_status_curve(cls, base_score: float, status: str) -> float:
        exponent = cls.STATUS_CURVE_EXPONENTS.get(status)
        if exponent is None:
            return base_score
        if base_score <= 0.0 or base_score >= 1.0:
            return base_score
        return max(0.0, min(1.0, base_score**exponent))

    @classmethod
    def _apply_governance_penalty(cls, score: float, penalty: float) -> float:
        if not penalty:
            return score
        adjusted = score + penalty
        return max(cls.MIN_SCORE, min(cls.MAX_SCORE, adjusted))


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
