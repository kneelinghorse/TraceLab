"""Shared dataclasses for the quality automation pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

Severity = Literal["low", "medium", "high"]
CheckStatus = Literal["passed", "warning", "failed"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class QualityIssue:
    """Structured issue reported by an automated checker."""

    code: str
    severity: Severity
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QualityAutomationCheckResult:
    """Outcome payload for each automated quality check."""

    check_type: str
    summary: str
    issues: List[QualityIssue] = field(default_factory=list)
    score: Optional[float] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=_utc_now)

    @property
    def status(self) -> CheckStatus:
        """Derive status from the most severe issue."""
        if any(issue.severity == "high" for issue in self.issues):
            return "failed"
        if self.issues:
            return "warning"
        return "passed"

    def to_details(self) -> Dict[str, Any]:
        """Convert to JSON-serialisable structure for persistence."""
        return {
            "summary": self.summary,
            "score": self.score,
            "metrics": dict(self.metrics),
            "issues": [
                {
                    "code": issue.code,
                    "severity": issue.severity,
                    "message": issue.message,
                    "metadata": issue.metadata or None,
                }
                for issue in self.issues
            ],
        }


__all__ = [
    "QualityIssue",
    "QualityAutomationCheckResult",
    "Severity",
    "CheckStatus",
]
