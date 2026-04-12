"""Transform Tracelab missions to PEDR manifest format.

Reference: cmos/planning/PEDR-docs/tracelab-to-pedr-mapping.md

This module provides backward-compatible manifest transformation while
integrating with the new Semantic Protocol for full protocol features.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.services.pedr.semantic_protocol import (
    Edge,
    ProtocolManifest,
    get_semantic_protocol,
)

# PII detection patterns (simple heuristics)
PII_PATTERNS = [
    re.compile(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b"),  # Full names
    re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),  # Phone numbers
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),  # Emails
    re.compile(r"\b\d{3}[-]?\d{2}[-]?\d{4}\b"),  # SSN
]


@dataclass(frozen=True)
class PEDRManifest:
    """PEDR protocol catalog entry format.

    This is the legacy manifest format maintained for backward compatibility.
    New code should use ProtocolManifest from semantic_protocol.py.
    """

    urn: str
    manifest: dict[str, Any]
    purpose: str
    description: str
    context_domain: str
    element_type: str
    element_intent: str
    governance_pii: bool
    governance_impact: int
    bindings: dict[str, Any]
    # New fields from Semantic Protocol
    confidence: float = 0.5
    criticality: float = 0.5
    semantic_vector: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
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
            "confidence": self.confidence,
            "criticality": self.criticality,
            "semantic_vector": self.semantic_vector,
        }

    @classmethod
    def from_protocol_manifest(
        cls, protocol_manifest: ProtocolManifest
    ) -> PEDRManifest:
        """Create PEDRManifest from a ProtocolManifest.

        Args:
            protocol_manifest: Full Semantic Protocol manifest

        Returns:
            Legacy PEDRManifest format
        """
        return cls(
            urn=str(protocol_manifest.urn),
            manifest=protocol_manifest.to_dict(),
            purpose=protocol_manifest.semantics.purpose,
            description=protocol_manifest.semantics.description,
            context_domain=protocol_manifest.context.get("domain", "research"),
            element_type=protocol_manifest.element.element_type.replace(
                "research.", ""
            ),
            element_intent=protocol_manifest.element.intent.value,
            governance_pii=protocol_manifest.governance.pii_handling,
            governance_impact=protocol_manifest.governance.business_impact,
            bindings=protocol_manifest.relationships,
            confidence=protocol_manifest.confidence,
            criticality=protocol_manifest.criticality,
            semantic_vector=protocol_manifest.semantics.vector,
        )


@dataclass
class TransformationResult:
    """Result of a manifest transformation."""

    success: bool
    manifest: PEDRManifest | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


class ManifestTransformer:
    """Transform Tracelab entities to PEDR manifest format."""

    EDGE_VIA_OPTIONS = {"api", "ui", "data"}

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
        mission_data: dict[str, Any],
        quality_gates: dict[str, Any] | None = None,
        project_id: str | None = None,
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
        warnings: list[str] = []

        if not mission_data:
            return TransformationResult(
                success=False,
                error="Mission data is empty",
            )

        # Extract mission protocol ID
        protocol_id = (
            mission_data.get("missionId")
            or mission_data.get("mission_id")
            or str(mission_id)
        )

        # Build URN
        urn = f"urn:research:mission:{protocol_id}"

        # Extract purpose from research statement
        research_statement = (
            mission_data.get("researchStatement")
            or mission_data.get("research_statement")
            or {}
        )
        objective = (
            research_statement.get("objective")
            or research_statement.get("purpose")
            or ""
        )
        if not objective:
            objective = mission_data.get("objective") or ""
            if not objective:
                warnings.append("No research statement objective found")

        # Extract description (title)
        title = (
            mission_data.get("name")
            or mission_data.get("title")
            or mission_data.get("metadata", {}).get("name")
            or protocol_id
        )

        # Detect PII in synthesis and content
        pii_flagged = self._detect_pii(mission_data)

        # Calculate governance impact score
        impact = self._calculate_impact(status, quality_gates, mission_data)

        # Extract bindings (relationships)
        bindings = self._extract_bindings(mission_data, project_id)
        edges = self._build_mission_edges(urn, mission_data, project_id)

        # Build the full manifest (for PEDR storage)
        full_manifest = {
            "id": str(mission_id),
            "protocol_id": protocol_id,
            "status": status,
            "research_statement": research_statement,
            "quality_gates": quality_gates,
            "created_at": mission_data.get("created_at")
            or mission_data.get("metadata", {}).get("created"),
            "updated_at": mission_data.get("updated_at"),
            "relationships": self._relationships_from_edges(edges),
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
        content: str | None = None,
        file_type: str | None = None,
        source_type: str | None = None,
        project_id: str | None = None,
        chunk_count: int = 0,
        uploaded_at: datetime | None = None,
        source_report_id: str | None = None,
        source_mission_id: str | None = None,
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
            "source_report_id": str(source_report_id) if source_report_id else None,
            "source_mission_id": str(source_mission_id) if source_mission_id else None,
            "uploaded_at": uploaded_at.isoformat() if uploaded_at else None,
            "relationships": self._relationships_from_edges(
                self._build_document_edges(
                    urn,
                    document_id,
                    project_id,
                    chunk_count,
                    source_type,
                    source_report_id,
                    source_mission_id,
                )
            ),
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
                "source_report_id": str(source_report_id) if source_report_id else None,
                "source_mission_id": str(source_mission_id)
                if source_mission_id
                else None,
            },
        )

        return TransformationResult(success=True, manifest=manifest)

    def transform_insight(
        self,
        insight_id: str,
        title: str,
        content: str,
        insight_type: str | None = None,
        created_by: str | None = None,
        validated: bool = False,
        project_id: str | None = None,
        source_chunk_ids: list[str] | None = None,
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
            "relationships": self._relationships_from_edges(
                self._build_insight_edges(urn, project_id, source_chunk_ids)
            ),
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

    def transform_report(
        self,
        report_id: str,
        title: str,
        content: str,
        *,
        project_id: str | None = None,
        source_chunk_ids: list[str] | None = None,
        source_collection_ids: list[str] | None = None,
        status: str | None = None,
    ) -> TransformationResult:
        """Transform a report to PEDR manifest format."""
        urn = f"urn:research:report:{report_id}"

        pii_flagged = self._detect_pii_in_text(content)

        full_manifest = {
            "id": str(report_id),
            "title": title,
            "status": status,
            "project_id": str(project_id) if project_id else None,
            "relationships": self._relationships_from_edges(
                self._build_report_edges(
                    urn,
                    project_id,
                    source_chunk_ids,
                    source_collection_ids,
                )
            ),
        }

        manifest = PEDRManifest(
            urn=urn,
            manifest=full_manifest,
            purpose=title,
            description=self._truncate(content, 500),
            context_domain="research",
            element_type="report",
            element_intent="Read",
            governance_pii=pii_flagged,
            governance_impact=self.BASE_IMPACT,
            bindings={
                "project_id": str(project_id) if project_id else None,
                "source_chunks": source_chunk_ids or [],
                "source_collections": source_collection_ids or [],
            },
        )

        return TransformationResult(success=True, manifest=manifest)

    def _detect_pii(self, mission_data: dict[str, Any]) -> bool:
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

    def _detect_pii_in_text(self, text: str | None) -> bool:
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
        quality_gates: dict[str, Any] | None,
        mission_data: dict[str, Any],
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
        mission_data: dict[str, Any],
        project_id: str | None,
    ) -> dict[str, Any]:
        """Extract relationship bindings from mission data."""
        bindings: dict[str, Any] = {}

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
            doc_ids = []
            for item in documents:
                doc_id, _ = self._extract_document_binding(item)
                if doc_id:
                    doc_ids.append(str(doc_id))
            if doc_ids:
                bindings["related_documents"] = doc_ids

        # Extract related mission references
        related = mission_data.get("related_missions", [])
        if isinstance(related, list):
            mission_ids = []
            for item in related:
                mission_id, _ = self._extract_mission_binding(item)
                if mission_id:
                    mission_ids.append(str(mission_id))
            if mission_ids:
                bindings["related_missions"] = mission_ids

        return bindings

    def _normalize_via(self, value: str | None) -> str | None:
        if not value:
            return None
        candidate = str(value).strip().lower()
        if candidate in self.EDGE_VIA_OPTIONS:
            return candidate
        return None

    def _to_urn(self, entity_type: str, identifier: str | None) -> str | None:
        if not identifier:
            return None
        value = str(identifier)
        if value.startswith("urn:"):
            return value
        return f"urn:research:{entity_type}:{value}"

    def _build_edge(
        self,
        edge_type: str,
        from_urn: str,
        to_urn: str,
        *,
        via: str | None = None,
    ) -> Edge | None:
        if not from_urn or not to_urn:
            return None
        return Edge(
            edge_type=edge_type,
            from_urn=from_urn,
            to_urn=to_urn,
            via=self._normalize_via(via),
        )

    def _relationships_from_edges(self, edges: Sequence[Edge]) -> dict[str, Any]:
        relationships: dict[str, list[str]] = {}
        for edge in edges:
            if edge.edge_type not in relationships:
                relationships[edge.edge_type] = []
            if edge.to_urn not in relationships[edge.edge_type]:
                relationships[edge.edge_type].append(edge.to_urn)
        relationships["edges"] = [edge.to_dict() for edge in edges]
        return relationships

    def _extract_chunk_binding(self, item: Any) -> tuple[str | None, str | None]:
        if isinstance(item, dict):
            chunk_id = item.get("chunk_id") or item.get("chunkId") or item.get("chunk")
            via = (
                item.get("via")
                or item.get("binding")
                or item.get("source_type")
                or item.get("source")
            )
            return (str(chunk_id) if chunk_id else None, self._normalize_via(via))
        if isinstance(item, str):
            return (item, None)
        return (None, None)

    def _extract_insight_binding(self, item: Any) -> tuple[str | None, str | None]:
        if isinstance(item, dict):
            insight_id = (
                item.get("insight_id") or item.get("insightId") or item.get("insight")
            )
            via = (
                item.get("via")
                or item.get("binding")
                or item.get("source_type")
                or item.get("source")
            )
            return (str(insight_id) if insight_id else None, self._normalize_via(via))
        if isinstance(item, str):
            return (item, None)
        return (None, None)

    def _extract_document_binding(self, item: Any) -> tuple[str | None, str | None]:
        if isinstance(item, dict):
            doc_id = (
                item.get("document_id")
                or item.get("documentId")
                or item.get("collection_id")
                or item.get("collectionId")
                or item.get("doc_id")
                or item.get("docId")
                or item.get("id")
                or item.get("document")
            )
            via = (
                item.get("via")
                or item.get("binding")
                or item.get("source_type")
                or item.get("source")
            )
            return (str(doc_id) if doc_id else None, self._normalize_via(via))
        if isinstance(item, str):
            return (item, None)
        return (None, None)

    def _extract_mission_binding(self, item: Any) -> tuple[str | None, str | None]:
        if isinstance(item, dict):
            mission_id = (
                item.get("mission_id")
                or item.get("missionId")
                or item.get("id")
                or item.get("mission")
            )
            via = (
                item.get("via")
                or item.get("binding")
                or item.get("source_type")
                or item.get("source")
            )
            return (str(mission_id) if mission_id else None, self._normalize_via(via))
        if isinstance(item, str):
            return (item, None)
        return (None, None)

    def _build_mission_edges(
        self,
        urn: str,
        mission_data: dict[str, Any],
        project_id: str | None,
    ) -> list[Edge]:
        edges: list[Edge] = []

        if project_id:
            project_urn = self._to_urn("project", project_id)
            edge = self._build_edge("belongs_to", urn, project_urn)
            if edge:
                edges.append(edge)

        evidence = mission_data.get("evidence") or []
        if isinstance(evidence, list):
            for item in evidence:
                chunk_id, via = self._extract_chunk_binding(item)
                chunk_urn = self._to_urn("chunk", chunk_id)
                edge = self._build_edge("evidence", urn, chunk_urn, via=via)
                if edge:
                    edges.append(edge)
                insight_id, insight_via = self._extract_insight_binding(item)
                insight_urn = self._to_urn("insight", insight_id)
                edge = self._build_edge("evidence", urn, insight_urn, via=insight_via)
                if edge:
                    edges.append(edge)

        documents = (
            mission_data.get("documents") or mission_data.get("related_documents") or []
        )
        if isinstance(documents, list):
            for item in documents:
                doc_id, via = self._extract_document_binding(item)
                doc_urn = self._to_urn("document", doc_id)
                edge = self._build_edge("references", urn, doc_urn, via=via)
                if edge:
                    edges.append(edge)

        related = (
            mission_data.get("related_missions")
            or mission_data.get("relatedMissions")
            or []
        )
        if isinstance(related, list):
            for item in related:
                mission_id, via = self._extract_mission_binding(item)
                mission_urn = self._to_urn("mission", mission_id)
                edge = self._build_edge("related_to", urn, mission_urn, via=via)
                if edge:
                    edges.append(edge)

        result_documents = (
            mission_data.get("result_document_ids")
            or mission_data.get("resultDocumentIds")
            or []
        )
        if isinstance(result_documents, list):
            for item in result_documents:
                doc_id, via = self._extract_document_binding(item)
                doc_urn = self._to_urn("document", doc_id)
                edge = self._build_edge("references", urn, doc_urn, via=via)
                if edge:
                    edges.append(edge)

        result_report_id = mission_data.get("result_report_id") or mission_data.get(
            "resultReportId"
        )
        report_urn = self._to_urn("report", result_report_id)
        edge = self._build_edge("references", urn, report_urn)
        if edge:
            edges.append(edge)

        return edges

    def _build_document_edges(
        self,
        urn: str,
        document_id: str,
        project_id: str | None,
        chunk_count: int,
        source_type: str | None,
        source_report_id: str | None = None,
        source_mission_id: str | None = None,
    ) -> list[Edge]:
        edges: list[Edge] = []
        via = self._normalize_via(source_type)

        if project_id:
            project_urn = self._to_urn("project", project_id)
            edge = self._build_edge("belongs_to", urn, project_urn, via=via)
            if edge:
                edges.append(edge)

        try:
            count = int(chunk_count or 0)
        except (TypeError, ValueError):
            count = 0

        for chunk_index in range(max(0, count)):
            chunk_id = f"{document_id}-chunk-{chunk_index}"
            chunk_urn = self._to_urn("chunk", chunk_id)
            edge = self._build_edge("contains", urn, chunk_urn, via=via)
            if edge:
                edges.append(edge)
            part_edge = self._build_edge("part_of", chunk_urn, urn, via=via)
            if part_edge:
                edges.append(part_edge)

        report_urn = self._to_urn("report", source_report_id)
        edge = self._build_edge("derived_from", urn, report_urn)
        if edge:
            edges.append(edge)

        mission_urn = self._to_urn("mission", source_mission_id)
        edge = self._build_edge("derived_from", urn, mission_urn)
        if edge:
            edges.append(edge)

        return edges

    def _build_insight_edges(
        self,
        urn: str,
        project_id: str | None,
        source_chunk_ids: list[str] | None,
    ) -> list[Edge]:
        edges: list[Edge] = []

        if project_id:
            project_urn = self._to_urn("project", project_id)
            edge = self._build_edge("belongs_to", urn, project_urn)
            if edge:
                edges.append(edge)

        for item in source_chunk_ids or []:
            chunk_id, via = self._extract_chunk_binding(item)
            chunk_urn = self._to_urn("chunk", chunk_id)
            edge = self._build_edge("derived_from", urn, chunk_urn, via=via)
            if edge:
                edges.append(edge)

        return edges

    def _build_report_edges(
        self,
        urn: str,
        project_id: str | None,
        source_chunk_ids: list[str] | None,
        source_collection_ids: list[str] | None = None,
    ) -> list[Edge]:
        edges: list[Edge] = []

        if project_id:
            project_urn = self._to_urn("project", project_id)
            edge = self._build_edge("belongs_to", urn, project_urn)
            if edge:
                edges.append(edge)

        for item in source_chunk_ids or []:
            chunk_id, via = self._extract_chunk_binding(item)
            chunk_urn = self._to_urn("chunk", chunk_id)
            edge = self._build_edge("references", urn, chunk_urn, via=via)
            if edge:
                edges.append(edge)

        for item in source_collection_ids or []:
            collection_id, via = self._extract_document_binding(item)
            collection_urn = self._to_urn("collection", collection_id)
            edge = self._build_edge("references", urn, collection_urn, via=via)
            if edge:
                edges.append(edge)

        return edges

    @staticmethod
    def _truncate(text: str | None, max_length: int) -> str:
        """Truncate text to max length with ellipsis."""
        if not text:
            return ""
        text = str(text).strip()
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    # ------------------------------------------------------------------
    # Semantic Protocol Integration
    # ------------------------------------------------------------------

    def transform_with_protocol(
        self,
        mission_id: str,
        mission_data: dict[str, Any],
        quality_gates: dict[str, Any] | None = None,
        project_id: str | None = None,
        status: str = "unknown",
    ) -> TransformationResult:
        """Transform mission using full Semantic Protocol.

        This method creates a ProtocolManifest with all semantic features:
        - URN-based identification
        - Bayesian confidence scoring
        - Criticality calculation
        - Semantic vectors

        Args:
            mission_id: Mission protocol ID
            mission_data: Full mission data
            quality_gates: Quality gate validation results
            project_id: Associated project ID
            status: Mission status

        Returns:
            TransformationResult with enhanced PEDRManifest
        """
        warnings: list[str] = []

        if not mission_data:
            return TransformationResult(
                success=False,
                error="Mission data is empty",
            )

        try:
            # Get semantic protocol service
            protocol = get_semantic_protocol()

            # Create full protocol manifest
            protocol_manifest = protocol.create_mission_manifest(
                mission_id=mission_id,
                mission_data=mission_data,
                quality_gates=quality_gates,
                project_id=project_id,
                status=status,
            )
            edges = self._build_mission_edges(
                str(protocol_manifest.urn),
                mission_data,
                project_id,
            )
            if edges:
                for edge in edges:
                    protocol_manifest.add_edge(edge)
                protocol._apply_hashes(protocol_manifest)

            # Convert to legacy PEDRManifest format
            legacy_manifest = PEDRManifest.from_protocol_manifest(protocol_manifest)

            return TransformationResult(
                success=True,
                manifest=legacy_manifest,
                warnings=warnings,
            )

        except Exception as e:
            # Fall back to legacy transformation
            warnings.append(f"Semantic Protocol failed, using legacy: {e}")
            return self.transform_mission(
                mission_id=mission_id,
                mission_data=mission_data,
                quality_gates=quality_gates,
                project_id=project_id,
                status=status,
            )

    def transform_document_with_protocol(
        self,
        document_id: str,
        name: str,
        content: str | None = None,
        file_type: str | None = None,
        source_type: str | None = None,
        project_id: str | None = None,
        chunk_count: int = 0,
        source_report_id: str | None = None,
        source_mission_id: str | None = None,
    ) -> TransformationResult:
        """Transform document using full Semantic Protocol.

        Args:
            document_id: Document ID
            name: Document name
            content: Document content
            file_type: File type
            source_type: Source type
            project_id: Associated project ID
            chunk_count: Number of chunks

        Returns:
            TransformationResult with enhanced PEDRManifest
        """
        try:
            protocol = get_semantic_protocol()

            protocol_manifest = protocol.create_document_manifest(
                document_id=document_id,
                name=name,
                content=content,
                file_type=file_type,
                source_type=source_type,
                project_id=project_id,
                chunk_count=chunk_count,
            )
            edges = self._build_document_edges(
                str(protocol_manifest.urn),
                document_id,
                project_id,
                chunk_count,
                source_type,
                source_report_id,
                source_mission_id,
            )
            if edges:
                for edge in edges:
                    protocol_manifest.add_edge(edge)
                protocol._apply_hashes(protocol_manifest)

            legacy_manifest = PEDRManifest.from_protocol_manifest(protocol_manifest)

            return TransformationResult(
                success=True,
                manifest=legacy_manifest,
            )

        except Exception:
            # Fall back to legacy transformation
            return self.transform_document(
                document_id=document_id,
                name=name,
                content=content,
                file_type=file_type,
                source_type=source_type,
                project_id=project_id,
                chunk_count=chunk_count,
            )

    def transform_insight_with_protocol(
        self,
        insight_id: str,
        title: str,
        content: str,
        insight_type: str | None = None,
        created_by: str | None = None,
        validated: bool = False,
        project_id: str | None = None,
        source_chunk_ids: list[str] | None = None,
    ) -> TransformationResult:
        """Transform insight using full Semantic Protocol.

        Args:
            insight_id: Insight ID
            title: Insight title
            content: Insight content
            insight_type: Type of insight
            created_by: Creator identifier
            validated: Validation status
            project_id: Associated project ID
            source_chunk_ids: Source chunk IDs

        Returns:
            TransformationResult with enhanced PEDRManifest
        """
        try:
            protocol = get_semantic_protocol()

            protocol_manifest = protocol.create_insight_manifest(
                insight_id=insight_id,
                title=title,
                content=content,
                insight_type=insight_type,
                validated=validated,
                project_id=project_id,
                source_chunk_ids=source_chunk_ids,
            )
            edges = self._build_insight_edges(
                str(protocol_manifest.urn),
                project_id,
                source_chunk_ids,
            )
            if edges:
                for edge in edges:
                    protocol_manifest.add_edge(edge)
                protocol._apply_hashes(protocol_manifest)

            legacy_manifest = PEDRManifest.from_protocol_manifest(protocol_manifest)

            return TransformationResult(
                success=True,
                manifest=legacy_manifest,
            )

        except Exception:
            # Fall back to legacy transformation
            return self.transform_insight(
                insight_id=insight_id,
                title=title,
                content=content,
                insight_type=insight_type,
                created_by=created_by,
                validated=validated,
                project_id=project_id,
                source_chunk_ids=source_chunk_ids,
            )


# Singleton instance
_transformer: ManifestTransformer | None = None


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
