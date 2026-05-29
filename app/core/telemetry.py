"""Unified telemetry envelope for all TraceLab JSONL event files.

Provides a standard event envelope with consistent fields across all telemetry
sources (PEDR, quality gates, caching, sync events, cost monitoring, etc.).

Envelope schema:
    {
        "ts":         ISO-8601 timestamp,
        "event_type": dotted event type string,
        "source":     "tracelab" | "cmos" | "pedr" | "quality" | "script",
        "sprint_id":  optional sprint reference,
        "payload":    original event-specific data
    }

Usage:
    from app.core.telemetry import emit_telemetry, TelemetryEnvelope

    emit_telemetry(
        path=Path("telemetry/events/my-events.jsonl"),
        event_type="pedr.search.completed",
        source="pedr",
        payload={"query": "...", "results": 5},
        sprint_id="sprint-35",
    )
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Valid source identifiers
VALID_SOURCES = frozenset({"tracelab", "cmos", "pedr", "quality", "script"})


def _utc_now() -> str:
    """Return ISO-8601 timestamp in UTC."""
    return datetime.now(tz=UTC).isoformat()


@dataclass
class TelemetryEnvelope:
    """Unified telemetry event envelope.

    All telemetry events should be wrapped in this envelope to ensure
    consistent downstream parsing by cmos-dashboard, analytics, and
    aggregation tooling.
    """

    ts: str
    event_type: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    sprint_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "ts": self.ts,
            "event_type": self.event_type,
            "source": self.source,
            "payload": self.payload,
        }
        if self.sprint_id:
            d["sprint_id"] = self.sprint_id
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def wrap(
        cls,
        event_type: str,
        source: str,
        payload: dict[str, Any],
        *,
        ts: str | None = None,
        sprint_id: str | None = None,
    ) -> TelemetryEnvelope:
        """Create an envelope wrapping an existing payload."""
        return cls(
            ts=ts or _utc_now(),
            event_type=event_type,
            source=source,
            payload=payload,
            sprint_id=sprint_id,
        )

    @classmethod
    def from_legacy(
        cls,
        raw: dict[str, Any],
        *,
        event_type: str | None = None,
        source: str = "tracelab",
    ) -> TelemetryEnvelope:
        """Wrap a legacy (pre-standardization) event in the envelope.

        Extracts ``ts`` and ``event_type`` from the raw event if present,
        then moves everything else into ``payload``.
        """
        ts = raw.pop("ts", None) or _utc_now()
        resolved_event_type = (
            event_type
            or raw.pop("event_type", None)
            or raw.pop("event", None)
            or raw.pop("type", None)
            or "unknown"
        )
        sprint_id = raw.pop("sprint_id", None)

        return cls(
            ts=ts,
            event_type=resolved_event_type,
            source=source,
            payload=raw,
            sprint_id=sprint_id,
        )


def emit_telemetry(
    *,
    path: Path,
    event_type: str,
    source: str,
    payload: dict[str, Any],
    sprint_id: str | None = None,
) -> bool:
    """Write a telemetry event in the unified envelope format.

    Creates parent directories if needed. Returns True on success.
    Silently logs and returns False on failure — telemetry must never
    crash the caller.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = TelemetryEnvelope.wrap(
            event_type=event_type,
            source=source,
            payload=payload,
            sprint_id=sprint_id,
        )
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(envelope.to_json() + "\n")
        return True
    except Exception as exc:
        logger.warning("Telemetry write failed (%s): %s", path, exc)
        return False


def is_envelope_format(event: dict[str, Any]) -> bool:
    """Check if an event dict conforms to the unified envelope schema."""
    required = {"ts", "event_type", "source", "payload"}
    return required.issubset(event.keys()) and isinstance(event.get("payload"), dict)


def validate_jsonl_file(path: Path) -> dict[str, Any]:
    """Validate a JSONL file for envelope conformance.

    Returns a summary dict with total lines, conforming count, and
    any violations found.
    """
    total = 0
    conforming = 0
    violations: list[dict[str, Any]] = []

    if not path.exists():
        return {"path": str(path), "exists": False, "total": 0}

    with open(path, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                violations.append({"line": line_no, "error": "invalid JSON"})
                continue

            if is_envelope_format(event):
                conforming += 1
            else:
                missing = {"ts", "event_type", "source", "payload"} - set(event.keys())
                violations.append(
                    {
                        "line": line_no,
                        "error": "missing envelope fields",
                        "missing": sorted(missing),
                    }
                )

    return {
        "path": str(path),
        "exists": True,
        "total": total,
        "conforming": conforming,
        "violations": len(violations),
        "conformance_rate": conforming / total if total else 1.0,
        "first_violations": violations[:5],
    }
