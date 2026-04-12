"""Auto-report service for creating reports from DeepSearch result protocols.

Automatically creates a Report from result_protocol when a mission completes,
linking it to the mission and associating sources from ingested document chunks.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.chunk import DocumentChunk
from app.models.mission import Mission
from app.models.report import Report, ReportSource

logger = logging.getLogger(__name__)


class AutoReportError(RuntimeError):
    """Raised when auto-report creation fails."""


def format_protocol_to_markdown(protocol: dict[str, Any], mission_title: str) -> str:
    """Format a result_protocol into readable markdown content.

    Args:
        protocol: The result_protocol dict from DeepSearch
        mission_title: The mission title for the header

    Returns:
        Formatted markdown string
    """
    lines: list[str] = []

    # Header
    lines.append(f"# Research: {mission_title}")
    lines.append("")

    # Synthesis / Summary
    if "synthesis" in protocol:
        synthesis = protocol["synthesis"]
        if isinstance(synthesis, str):
            lines.append("## Summary")
            lines.append("")
            lines.append(synthesis)
            lines.append("")
        elif isinstance(synthesis, dict):
            if synthesis.get("summary"):
                lines.append("## Summary")
                lines.append("")
                lines.append(synthesis["summary"])
                lines.append("")
            if synthesis.get("key_findings"):
                lines.append("### Key Findings")
                lines.append("")
                for finding in synthesis["key_findings"]:
                    if isinstance(finding, str):
                        lines.append(f"- {finding}")
                    elif isinstance(finding, dict):
                        lines.append(
                            f"- **{finding.get('title', 'Finding')}**: {finding.get('description', '')}"
                        )
                lines.append("")

    # Findings section
    if "findings" in protocol:
        lines.append("## Findings")
        lines.append("")
        for i, finding in enumerate(protocol["findings"], 1):
            if isinstance(finding, str):
                lines.append(f"{i}. {finding}")
            elif isinstance(finding, dict):
                title = finding.get("title", f"Finding {i}")
                desc = finding.get("description", finding.get("content", ""))
                confidence = finding.get("confidence")
                lines.append(f"### {title}")
                if confidence:
                    lines.append(f"*Confidence: {confidence:.0%}*")
                lines.append("")
                lines.append(desc)
                lines.append("")

    # Sources section
    if "sources" in protocol:
        lines.append("## Sources")
        lines.append("")
        for source in protocol["sources"]:
            if isinstance(source, str):
                lines.append(f"- {source}")
            elif isinstance(source, dict):
                url = source.get("url", source.get("link", ""))
                title = source.get("title", url)
                relevance = source.get("relevance")
                if url:
                    entry = f"- [{title}]({url})"
                else:
                    entry = f"- {title}"
                if relevance:
                    entry += f" *(relevance: {relevance:.0%})*"
                lines.append(entry)
        lines.append("")

    # Quality checkpoints
    if "quality_checkpoints" in protocol:
        lines.append("## Quality Checkpoints")
        lines.append("")
        for checkpoint in protocol["quality_checkpoints"]:
            if isinstance(checkpoint, str):
                lines.append(f"- [x] {checkpoint}")
            elif isinstance(checkpoint, dict):
                name = checkpoint.get("name", "Checkpoint")
                status = checkpoint.get("status", "passed")
                icon = "[x]" if status == "passed" else "[ ]"
                lines.append(f"- {icon} {name}")
        lines.append("")

    # Raw protocol data as fallback
    if not any(key in protocol for key in ("synthesis", "findings", "sources")):
        # No standard structure, dump as readable format
        lines.append("## Protocol Data")
        lines.append("")
        lines.append("```json")
        import json

        lines.append(json.dumps(protocol, indent=2))
        lines.append("```")
        lines.append("")

    # Metadata footer
    lines.append("---")
    lines.append(
        f"*Generated automatically from DeepSearch results at {datetime.utcnow().isoformat()}Z*"
    )

    return "\n".join(lines)


def get_document_chunks(
    db: Session, document_id: UUID, limit: int = 10
) -> list[DocumentChunk]:
    """Get chunks from a document for source linking.

    Args:
        db: Database session
        document_id: Document UUID
        limit: Maximum number of chunks to return

    Returns:
        List of DocumentChunk objects
    """
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == str(document_id))
        .order_by(DocumentChunk.chunk_index)
        .limit(limit)
        .all()
    )
    return chunks


def create_report_from_protocol(
    db: Session,
    mission: Mission,
    protocol: dict[str, Any],
) -> Report:
    """Create a Report from result_protocol when mission completes.

    Creates a report with:
    - Title derived from mission title
    - Content formatted from protocol
    - Sources linked to ingested document chunks
    - Status: draft (user can finalize)

    Args:
        db: Database session
        mission: The completed mission with result_protocol
        protocol: The result_protocol dict

    Returns:
        The created Report

    Raises:
        AutoReportError: If report creation fails
    """
    if not protocol:
        raise AutoReportError("No protocol data to create report from")

    if not mission.project_id:
        raise AutoReportError(f"Mission {mission.mission_id} has no project_id")

    logger.info(
        "Creating auto-report for mission %s",
        mission.mission_id,
    )

    # Format protocol to markdown
    content = format_protocol_to_markdown(protocol, mission.title)

    # Compute content hash for dedup
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    # Build metadata
    metadata = {
        "mission_id": mission.mission_id,
        "auto_generated": True,
        "quality_checkpoints": protocol.get("quality_checkpoints", []),
    }
    if mission.deepsearch_job_id:
        metadata["deepsearch_job_id"] = mission.deepsearch_job_id

    # Create report
    report = Report(
        project_id=str(mission.project_id),
        title=f"Research: {mission.title}",
        report_type="markdown",
        prompt=f"Auto-generated from mission {mission.mission_id}",
        content=content,
        content_hash=content_hash,
        status="draft",
        tokens_used=0,  # Not from synthesis
        chunk_count=0,  # Will update after linking sources
    )
    db.add(report)
    db.flush()  # Get report.id

    logger.debug("Created report %s for mission %s", report.id, mission.mission_id)

    # Link sources from auto-ingested document chunks
    chunk_count = 0
    if mission.result_document_ids:
        for doc_id_str in mission.result_document_ids:
            try:
                doc_id = UUID(doc_id_str)
                chunks = get_document_chunks(db, doc_id, limit=10)
                for chunk in chunks:
                    source = ReportSource(
                        report_id=report.id,
                        source_type="chunk",
                        source_id=str(chunk.id),
                    )
                    db.add(source)
                    chunk_count += 1
                logger.debug(
                    "Linked %d chunks from document %s to report %s",
                    len(chunks),
                    doc_id,
                    report.id,
                )
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "Invalid document ID %s in mission %s: %s",
                    doc_id_str,
                    mission.mission_id,
                    exc,
                )

    # Update chunk count
    report.chunk_count = chunk_count

    # Update mission with report reference
    mission.result_report_id = report.id
    db.commit()
    db.refresh(report)

    logger.info(
        "Successfully created report %s for mission %s with %d source chunks",
        report.id,
        mission.mission_id,
        chunk_count,
    )

    return report


class AutoReportService:
    """Service for automatically creating reports from mission protocols."""

    def create_report_from_protocol(
        self,
        db: Session,
        mission: Mission,
        protocol: dict[str, Any],
    ) -> Report:
        """Create a Report from result_protocol.

        Wraps the module-level function for dependency injection.
        """
        return create_report_from_protocol(db, mission, protocol)


# Module-level singleton
_service: AutoReportService | None = None


def get_auto_report_service() -> AutoReportService:
    """Get or create the auto-report service instance."""
    global _service
    if _service is None:
        _service = AutoReportService()
    return _service
