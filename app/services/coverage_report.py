"""
Ingestion coverage report generator.

Generates a summary of ingestion success/failure counts per format.
"""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.document import Document


class CoverageReportGenerator:
    """Generates ingestion coverage reports."""

    def __init__(
        self,
        output_path: Path = Path(
            "cmos/reports/sprint-01/ingestion_format_coverage.json"
        ),
    ):
        """
        Initialize coverage report generator.

        Args:
            output_path: Path to save the coverage report JSON file
        """
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def generate_report(self, db: Session) -> dict[str, Any]:
        """
        Generate coverage report from database.

        Args:
            db: Database session

        Returns:
            Dictionary with coverage statistics per format
        """
        # Query all documents grouped by format
        documents = db.query(Document).all()

        # Group by file extension
        format_stats = defaultdict(
            lambda: {
                "total": 0,
                "success": 0,
                "failed": 0,
                "processed": 0,
                "chunked": 0,
                "embedded": 0,
            }
        )

        for doc in documents:
            # Extract file extension
            if doc.file_path:
                file_ext = Path(doc.file_path).suffix.lower()
            elif doc.name:
                file_ext = Path(doc.name).suffix.lower()
            else:
                file_ext = "unknown"

            # Initialize if not exists
            stats = format_stats[file_ext]
            stats["total"] += 1

            # Count by status
            if doc.processed:
                stats["processed"] += 1
            if doc.chunked:
                stats["chunked"] += 1
            if doc.embedded:
                stats["embedded"] += 1

            # Determine success/failure based on validation status
            if doc.validation_status == "validated":
                stats["success"] += 1
            elif doc.validation_status == "flagged":
                stats["failed"] += 1
            # For pending, count as neither success nor failed yet

        # Calculate percentages
        report = {"generated_at": datetime.utcnow().isoformat() + "Z", "formats": {}}

        for file_ext, stats in format_stats.items():
            format_name = (
                file_ext.lstrip(".").upper() if file_ext != "unknown" else "UNKNOWN"
            )

            success_rate = (
                (stats["success"] / stats["total"] * 100) if stats["total"] > 0 else 0
            )
            processed_rate = (
                (stats["processed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            )
            chunked_rate = (
                (stats["chunked"] / stats["total"] * 100) if stats["total"] > 0 else 0
            )

            report["formats"][format_name] = {
                "extension": file_ext,
                "total_uploaded": stats["total"],
                "successfully_processed": stats["success"],
                "failed": stats["failed"],
                "processed": stats["processed"],
                "chunked": stats["chunked"],
                "embedded": stats["embedded"],
                "success_rate_percent": round(success_rate, 2),
                "processed_rate_percent": round(processed_rate, 2),
                "chunked_rate_percent": round(chunked_rate, 2),
            }

        # Save to file
        with open(self.output_path, "w") as f:
            json.dump(report, f, indent=2)

        return report
