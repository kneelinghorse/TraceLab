"""Pre-flight query service for duplicate research prevention.

Enables DeepSearch to check TraceLab before launching new research missions.
Returns reuse recommendations based on similarity and quality thresholds.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.mission import Mission
from app.models.project import Project
from app.models.document import Document
from app.schemas.pedr_preflight import (
    PreflightMatch,
    PreflightMatchInsight,
    PreflightQuery,
    PreflightRecommendation,
    PreflightTelemetry,
)
from app.services.pedr.quality_scoring import QualityFilters

if TYPE_CHECKING:
    from app.services.hybrid_search import HybridSearchService

logger = logging.getLogger(__name__)


@dataclass
class PreflightThresholds:
    """Decision thresholds for pre-flight recommendations."""

    reuse_similarity: float = 0.85
    reuse_min_gates: int = 4
    review_similarity: float = 0.70
    proceed_below: float = 0.70


class PreflightService:
    """Execute pre-flight queries and generate reuse recommendations."""

    DEFAULT_THRESHOLDS = PreflightThresholds()
    TELEMETRY_DIR = Path("cmos/telemetry/events")

    def __init__(
        self,
        *,
        search_service: Optional["HybridSearchService"] = None,
        session_factory: Callable[[], Session] = SessionLocal,
        thresholds: Optional[PreflightThresholds] = None,
        telemetry_enabled: bool = True,
    ) -> None:
        if search_service is None:
            # Lazy import to avoid circular dependency
            from app.services.hybrid_search import get_hybrid_search_service
            search_service = get_hybrid_search_service()
        self.search_service = search_service
        self.session_factory = session_factory
        self.thresholds = thresholds or self.DEFAULT_THRESHOLDS
        self.telemetry_enabled = telemetry_enabled

    def query(
        self,
        request: PreflightQuery,
        *,
        agent: str = "unknown",
    ) -> PreflightRecommendation:
        """Execute pre-flight query and return recommendation."""
        start_time = time.perf_counter()

        quality_filters = QualityFilters(
            min_quality_gates=request.min_quality_gates,
            statuses=tuple(request.status),
            allow_pii=True,
        )

        search_results = self.search_service.search(
            query=request.query,
            top_k=request.top_k * 2,
            search_mode="hybrid",
            min_quality_gates=request.min_quality_gates,
            status_filters=request.status,
        )

        matches = self._build_matches(search_results, request.similarity_threshold)

        action, summary = self._determine_recommendation(
            matches=matches,
            query=request.query,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        top_score = matches[0].similarity_score if matches else None

        recommendation = PreflightRecommendation(
            action=action,
            matches=matches[: request.top_k],
            summary=summary,
            top_score=top_score,
            match_count=len(matches),
            query=request.query,
            latency_ms=round(elapsed_ms, 2),
            filters_applied={
                "min_quality_gates": request.min_quality_gates,
                "status": request.status,
                "similarity_threshold": request.similarity_threshold,
            },
        )

        if self.telemetry_enabled:
            self._emit_telemetry(recommendation, agent=agent)

        return recommendation

    def _build_matches(
        self,
        search_results: List[Dict[str, Any]],
        min_similarity: float,
    ) -> List[PreflightMatch]:
        """Convert search results to PreflightMatch instances."""
        if not search_results:
            return []

        document_ids = [
            r.get("document_id")
            for r in search_results
            if r.get("document_id")
        ]
        if not document_ids:
            return []

        mission_map = self._load_mission_metadata(document_ids)

        seen_missions: set[str] = set()
        matches: List[PreflightMatch] = []

        for result in search_results:
            doc_id = result.get("document_id")
            if not doc_id or doc_id not in mission_map:
                continue

            metadata = mission_map[doc_id]
            mission_uuid = metadata.get("mission_uuid")
            if not mission_uuid or mission_uuid in seen_missions:
                continue

            similarity = float(result.get("score") or result.get("combined_score") or 0.0)
            if similarity < min_similarity:
                continue

            seen_missions.add(mission_uuid)
            match = self._build_single_match(metadata, similarity)
            if match:
                matches.append(match)

        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        return matches

    def _build_single_match(
        self,
        metadata: Dict[str, Any],
        similarity: float,
    ) -> Optional[PreflightMatch]:
        """Build a PreflightMatch from mission metadata."""
        mission_data = metadata.get("mission_data") or {}
        research_statement = mission_data.get("research_statement") or {}
        synthesis = mission_data.get("synthesis") or {}

        mission_id = mission_data.get("mission_id") or metadata.get("mission_id") or "unknown"
        title = mission_data.get("title") or research_statement.get("topic") or "Untitled"
        objective = research_statement.get("objective") or mission_data.get("objective") or ""
        if len(objective) > 200:
            objective = objective[:197] + "..."

        key_insights_raw = synthesis.get("key_insights") or []
        key_insights: List[PreflightMatchInsight] = []
        for i, insight in enumerate(key_insights_raw[:3]):
            if isinstance(insight, str) and insight.strip():
                text = insight.strip()
                if len(text) > 150:
                    text = text[:147] + "..."
                key_insights.append(PreflightMatchInsight(text=text, index=i))

        tags = mission_data.get("tags") or []
        if not isinstance(tags, list):
            tags = []

        created_at = metadata.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                created_at = None

        return PreflightMatch(
            mission_id=str(mission_id),
            mission_uuid=str(metadata.get("mission_uuid") or ""),
            title=str(title),
            objective=str(objective),
            status=str(metadata.get("status") or "unknown"),
            quality_gates_passed=int(metadata.get("quality_gates_passed") or 0),
            quality_gates_total=int(metadata.get("quality_gates_total") or 5),
            quality_score=float(metadata.get("quality_score") or 0.6),
            similarity_score=round(similarity, 4),
            key_insights=key_insights,
            created_at=created_at,
            tags=[str(t) for t in tags if isinstance(t, str)],
        )

    def _load_mission_metadata(
        self,
        document_ids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Load mission metadata for documents."""
        if not document_ids:
            return {}

        session = self.session_factory()
        try:
            parsed_ids = []
            for doc_id in document_ids:
                try:
                    parsed_ids.append(uuid.UUID(str(doc_id)))
                except (TypeError, ValueError):
                    continue

            if not parsed_ids:
                return {}

            rows = (
                session.query(
                    Document.id.label("document_id"),
                    Mission.id.label("mission_uuid"),
                    Mission.mission_data,
                    Mission.quality_gates,
                    Mission.status,
                    Mission.created_at,
                )
                .join(Project, Document.project_id == Project.id)
                .outerjoin(Mission, Project.mission_protocol_id == Mission.id)
                .filter(Document.id.in_(parsed_ids))
                .all()
            )

            result: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                payload = row._mapping
                doc_id = str(payload["document_id"])
                mission_data = payload["mission_data"] or {}
                quality_gates = payload["quality_gates"] or {}

                passed = self._count_passed_gates(quality_gates, mission_data)

                result[doc_id] = {
                    "document_id": doc_id,
                    "mission_uuid": str(payload["mission_uuid"]) if payload["mission_uuid"] else None,
                    "mission_data": mission_data,
                    "status": payload["status"],
                    "created_at": payload["created_at"],
                    "quality_gates_passed": passed,
                    "quality_gates_total": 5,
                    "quality_score": self._compute_quality_score(passed, payload["status"]),
                }

            return result
        finally:
            session.close()

    def _count_passed_gates(
        self,
        quality_gates: Dict[str, Any],
        mission_data: Dict[str, Any],
    ) -> int:
        """Count passing quality gates from stored metadata."""
        expected_gates = (
            "research_statement",
            "evidence_links",
            "synthesis_quality",
            "traceability",
            "contradictions_resolved",
        )
        passed = 0

        for gate in expected_gates:
            gate_data = quality_gates.get(gate) or {}
            status = str(gate_data.get("status") or "").lower()
            if status in ("pass", "passed", "complete"):
                passed += 1

        if passed < len(expected_gates):
            checkpoints = mission_data.get("quality_checkpoints") or []
            if isinstance(checkpoints, list):
                for checkpoint in checkpoints:
                    if not isinstance(checkpoint, dict):
                        continue
                    gate_name = str(checkpoint.get("gate") or "").lower()
                    checkpoint_status = str(checkpoint.get("status") or "").lower()
                    if gate_name in expected_gates and checkpoint_status in ("pass", "passed"):
                        if quality_gates.get(gate_name) is None:
                            passed += 1

        return min(passed, 5)

    def _compute_quality_score(self, passed_gates: int, status: Optional[str]) -> float:
        """Compute quality multiplier from gates and status."""
        base = passed_gates / 5.0 if passed_gates > 0 else 0.6
        boost = 0.0
        if status:
            status_lower = status.lower()
            if status_lower == "complete":
                boost = 0.20
            elif status_lower == "review":
                boost = 0.10
            elif status_lower == "in_progress":
                boost = 0.05
        return round(min(1.5, max(0.1, base * (1.0 + boost))), 4)

    def _determine_recommendation(
        self,
        matches: List[PreflightMatch],
        query: str,
    ) -> Tuple[str, str]:
        """Determine action and summary based on matches."""
        if not matches:
            return "proceed", f"No relevant existing research found for: '{query[:50]}...'"

        top = matches[0]
        score = top.similarity_score
        gates = top.quality_gates_passed

        if score >= self.thresholds.reuse_similarity and gates >= self.thresholds.reuse_min_gates:
            summary = (
                f"High-quality match found: '{top.title}' "
                f"(similarity: {score:.0%}, quality gates: {gates}/5). "
                "Recommend reusing existing research."
            )
            return "reuse", summary

        if score >= self.thresholds.review_similarity:
            summary = (
                f"Potential match found: '{top.title}' "
                f"(similarity: {score:.0%}, quality gates: {gates}/5). "
                "Review existing research before proceeding."
            )
            return "review", summary

        summary = f"No sufficiently relevant research found. Proceed with new research."
        return "proceed", summary

    def _emit_telemetry(
        self,
        recommendation: PreflightRecommendation,
        agent: str,
    ) -> None:
        """Write telemetry event for pre-flight query."""
        try:
            telemetry = PreflightTelemetry(
                timestamp=datetime.now(timezone.utc),
                query=recommendation.query,
                action=recommendation.action,
                top_score=recommendation.top_score,
                match_count=recommendation.match_count,
                latency_ms=recommendation.latency_ms,
                min_quality_gates=recommendation.filters_applied.get("min_quality_gates", 4),
                status_filters=recommendation.filters_applied.get("status", []),
                agent=agent,
            )

            self.TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
            telemetry_path = self.TELEMETRY_DIR / "sprint-11-preflight.jsonl"

            with telemetry_path.open("a", encoding="utf-8") as f:
                f.write(telemetry.model_dump_json())
                f.write("\n")
        except Exception as e:
            logger.warning("Failed to emit preflight telemetry: %s", e)


_preflight_service: Optional[PreflightService] = None


def get_preflight_service() -> PreflightService:
    """Return a singleton preflight service instance."""
    global _preflight_service
    if _preflight_service is None:
        _preflight_service = PreflightService()
    return _preflight_service


__all__ = [
    "PreflightThresholds",
    "PreflightService",
    "get_preflight_service",
]
