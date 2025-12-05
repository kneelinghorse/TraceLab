"""Transform Tracelab missions to PEDR manifest format.

Reference: cmos/planning/PEDR-docs/tracelab-to-pedr-mapping.md
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

# PII detection patterns (simple heuristics)
PII_PATTERNS = [
    re.compile(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b'),  # Full names
    re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'),  # Phone numbers
    re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),  # Emails
    re.compile(r'\b\d{3}[-]?\d{2}[-]?\d{4}\b'),  # SSN
]


@dataclass(frozen=True)
class PEDRManifest:
    """PEDR protocol catalog entry format."""

    urn: str
    manifest: Dict[str, Any]
    purpose: str
    description: str
    context_domain: str
    element_type: str
    element_intent: str
    governance_pii: bool
    governance_impact: int
    bindings: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "urn": self.urn,
            "manifest": self.manifest,
            "purpose": self.purpose,
            "description": self.description,
            "context_domain": self.context_domain,
            "element_type": self.element_type,
            "element_intent": self.element_intent,
            "governance_pii": self.governance_pii,
            "governance_impact": self.governance_impact,
            "bindings": self.bindings,
        }


@dataclass
class TransformationResult:
    """Result of a manifest transformation."""

    success: bool
    manifest: Optional[PEDRManifest] = None
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


class ManifestTransformer:
    """Transform Tracelab entities to PEDR manifest format."""

    # Impact scores based on quality gates
    BASE_IMPACT: int = 5
    COMPLETE_STATUS_BONUS: int = 2
    ALL_GATES_PASS_BONUS: int = 1
    VALIDATED_BONUS: int = 1
    MAX_IMPACT: int = 10
    MIN_IMPACT: int = 1

    # Expected quality gates
    EXPECTED_GATES: tuple[str, ...] = (
        "research_statement",
        "evidence_links",
        "synthesis_quality",
        "traceability",
        "contradictions_resolved",
    )

    def transform_mission(
        self,
        mission_id: str,
        mission_data: Dict[str, Any],
        quality_gates: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
        status: str = "unknown",
    ) -> TransformationResult:
        """Transform a mission to PEDR manifest format.

        Args:
            mission_id: Unique mission identifier
            mission_data: Full Mission Protocol YAML structure
            quality_gates: Quality gate validation results
            project_id: Associated project ID
            status: Mission status (draft, in_progress, review, complete)

        Returns:
            TransformationResult with manifest or error
        """
        warnings: List[str] = []

        if not mission_data:
            return TransformationResult(
                success=False,
                error="Mission data is empty",
            )

        # Extract mission protocol ID
        protocol_id = mission_data.get("missionId") or mission_data.get("mission_id") or str(mission_id)

        # Build URN
        urn = f"urn:research:mission:{protocol_id}"

        # Extract purpose from research statement
        research_statement = mission_data.get("researchStatement") or mission_data.get("research_statement") or {}
        objective = research_statement.get("objective") or research_statement.get("purpose") or ""
        if not objective:
            objective = mission_data.get("objective") or ""
            if not objective:
                warnings.append("No research statement objective found")

        # Extract description (title)
        title = (
            mission_data.get("name") or
            mission_data.get("title") or
            mission_data.get("metadata", {}).get("name") or
            protocol_id
        )

        # Detect PII in synthesis and content
        pii_flagged = self._detect_pii(mission_data)

        # Calculate governance impact score
        impact = self._calculate_impact(status, quality_gates, mission_data)

        # Extract bindings (relationships)
        bindings = self._extract_bindings(mission_data, project_id)

        # Build the full manifest (for PEDR storage)
        full_manifest = {
            "id": str(mission_id),
            "protocol_id": protocol_id,
            "status": status,
            "research_statement": research_statement,
            "quality_gates": quality_gates,
            "created_at": mission_data.get("created_at") or mission_data.get("metadata", {}).get("created"),
            "updated_at": mission_data.get("updated_at"),
        }

        manifest = PEDRManifest(
            urn=urn,
            manifest=full_manifest,
            purpose=self._truncate(objective, 500),
            description=self._truncate(title, 200),
            context_domain="research",
            element_type="mission",
            element_intent="Read",  # Missions are research artifacts (read-focused)
            governance_pii=pii_flagged,
            governance_impact=impact,
            bindings=bindings,
        )

        return TransformationResult(
            success=True,
            manifest=manifest,
            warnings=warnings,
        )

    def transform_document(
        self,
        document_id: str,
        name: str,
        content: Optional[str] = None,
        file_type: Optional[str] = None,
        source_type: Optional[str] = None,
        project_id: Optional[str] = None,
        chunk_count: int = 0,
        uploaded_at: Optional[datetime] = None,
    ) -> TransformationResult:
        """Transform a document to PEDR manifest format."""
        urn = f"urn:research:document:{document_id}"

        pii_flagged = self._detect_pii_in_text(content) if content else False

        full_manifest = {
            "id": str(document_id),
            "name": name,
            "file_type": file_type,
            "source_type": source_type,
            "project_id": str(project_id) if project_id else None,
            "uploaded_at": uploaded_at.isoformat() if uploaded_at else None,
        }

        manifest = PEDRManifest(
            urn=urn,
            manifest=full_manifest,
            purpose=f"Research document: {name}",
            description=self._truncate(content, 500) if content else name,
            context_domain="research",
            element_type=file_type or "document",
            element_intent="Read",
            governance_pii=pii_flagged,
            governance_impact=self.BASE_IMPACT,  # Default medium impact
            bindings={
                "project_id": str(project_id) if project_id else None,
                "chunk_count": chunk_count,
            },
        )

        return TransformationResult(success=True, manifest=manifest)

    def transform_insight(
        self,
        insight_id: str,
        title: str,
        content: str,
        insight_type: Optional[str] = None,
        created_by: Optional[str] = None,
        validated: bool = False,
        project_id: Optional[str] = None,
        source_chunk_ids: Optional[List[str]] = None,
    ) -> TransformationResult:
        """Transform an insight to PEDR manifest format."""
        urn = f"urn:research:insight:{insight_id}"

        pii_flagged = self._detect_pii_in_text(content)

        # Map insight type to intent
        intent_map = {
            "finding": "Read",
            "recommendation": "Execute",
            "contradiction": "Update",  # Needs resolution
        }
        intent = intent_map.get(insight_type or "", "Read")

        # Impact based on validation
        impact = 7 if validated else self.BASE_IMPACT

        full_manifest = {
            "id": str(insight_id),
            "title": title,
            "insight_type": insight_type,
            "created_by": created_by,
            "validated": validated,
            "project_id": str(project_id) if project_id else None,
        }

        manifest = PEDRManifest(
            urn=urn,
            manifest=full_manifest,
            purpose=title,
            description=self._truncate(content, 500),
            context_domain="research",
            element_type=insight_type or "insight",
            element_intent=intent,
            governance_pii=pii_flagged,
            governance_impact=impact,
            bindings={
                "project_id": str(project_id) if project_id else None,
                "source_chunks": source_chunk_ids or [],
            },
        )

        return TransformationResult(success=True, manifest=manifest)

    def _detect_pii(self, mission_data: Dict[str, Any]) -> bool:
        """Detect PII in mission data."""
        # Check explicit governance flags
        governance = mission_data.get("governance", {})
        if isinstance(governance, dict):
            for key in ("pii", "pii_flag", "pii_handling", "piiHandling"):
                if governance.get(key):
                    return True

        # Check top-level flags
        for key in ("pii", "pii_flag", "pii_handling"):
            if mission_data.get(key):
                return True

        # Check tags
        tags = mission_data.get("tags", [])
        if isinstance(tags, list):
            pii_tags = {"pii", "privacy", "redaction", "sensitive"}
            for tag in tags:
                if isinstance(tag, str) and tag.lower() in pii_tags:
                    return True

        # Check synthesis content for PII patterns
        synthesis = mission_data.get("synthesis", {})
        if isinstance(synthesis, dict):
            for field in ("key_insights", "recommendations", "summary"):
                content = synthesis.get(field)
                if isinstance(content, str) and self._detect_pii_in_text(content):
                    return True
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, str) and self._detect_pii_in_text(item):
                            return True

        return False

    def _detect_pii_in_text(self, text: Optional[str]) -> bool:
        """Detect PII patterns in text content."""
        if not text:
            return False

        # Check for common PII patterns
        for pattern in PII_PATTERNS:
            if pattern.search(text):
                return True

        return False

    def _calculate_impact(
        self,
        status: str,
        quality_gates: Optional[Dict[str, Any]],
        mission_data: Dict[str, Any],
    ) -> int:
        """Calculate governance impact score (1-10 range).

        Based on:
        - Base score: 5
        - Complete status: +2
        - All quality gates pass: +1
        - Validated mission: +1
        """
        impact = self.BASE_IMPACT

        # Status bonus
        if status.lower() == "complete":
            impact += self.COMPLETE_STATUS_BONUS

        # Quality gates bonus
        if quality_gates:
            passed = 0
            for gate in self.EXPECTED_GATES:
                gate_data = quality_gates.get(gate, {})
                if isinstance(gate_data, dict):
                    gate_status = str(gate_data.get("status", "")).lower()
                    if gate_status in ("pass", "passed", "complete"):
                        passed += 1

            if passed == len(self.EXPECTED_GATES):
                impact += self.ALL_GATES_PASS_BONUS

        # Check quality checkpoints in mission data
        checkpoints = mission_data.get("quality_checkpoints", [])
        if isinstance(checkpoints, list):
            validated = all(
                isinstance(cp, dict) and cp.get("status") == "pass"
                for cp in checkpoints
                if isinstance(cp, dict) and cp.get("gate") in self.EXPECTED_GATES
            )
            if validated and checkpoints:
                impact += self.VALIDATED_BONUS

        return min(self.MAX_IMPACT, max(self.MIN_IMPACT, impact))

    def _extract_bindings(
        self,
        mission_data: Dict[str, Any],
        project_id: Optional[str],
    ) -> Dict[str, Any]:
        """Extract relationship bindings from mission data."""
        bindings: Dict[str, Any] = {}

        if project_id:
            bindings["project_id"] = str(project_id)

        # Extract evidence chunk references
        evidence = mission_data.get("evidence", [])
        if isinstance(evidence, list):
            chunk_ids = []
            for item in evidence:
                if isinstance(item, dict):
                    chunk_id = item.get("chunk_id") or item.get("chunkId")
                    if chunk_id:
                        chunk_ids.append(str(chunk_id))
            if chunk_ids:
                bindings["evidence_chunks"] = chunk_ids

        # Extract document references
        documents = mission_data.get("documents", [])
        if isinstance(documents, list):
            doc_ids = [str(d.get("id") or d) for d in documents if d]
            if doc_ids:
                bindings["related_documents"] = doc_ids

        # Extract related mission references
        related = mission_data.get("related_missions", [])
        if isinstance(related, list):
            bindings["related_missions"] = [str(m) for m in related if m]

        return bindings

    @staticmethod
    def _truncate(text: Optional[str], max_length: int) -> str:
        """Truncate text to max length with ellipsis."""
        if not text:
            return ""
        text = str(text).strip()
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."


# Singleton instance
_transformer: Optional[ManifestTransformer] = None


def get_manifest_transformer() -> ManifestTransformer:
    """Return singleton manifest transformer instance."""
    global _transformer
    if _transformer is None:
        _transformer = ManifestTransformer()
    return _transformer


__all__ = [
    "PEDRManifest",
    "TransformationResult",
    "ManifestTransformer",
    "get_manifest_transformer",
]
