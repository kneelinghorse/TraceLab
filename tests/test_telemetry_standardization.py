"""Tests for T35.4 Sprint Telemetry Standardization.

Covers:
- TelemetryEnvelope creation, serialization, and validation
- Legacy event wrapping (from_legacy)
- emit_telemetry() file writing in envelope format
- is_envelope_format() detection
- validate_jsonl_file() conformance checking
- Migration script line-level migration
- Idempotent migration (already-migrated events untouched)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.telemetry import (
    TelemetryEnvelope,
    emit_telemetry,
    is_envelope_format,
    validate_jsonl_file,
)


# -------------------------------------------------------------------------
# TelemetryEnvelope tests
# -------------------------------------------------------------------------


class TestTelemetryEnvelope:
    """Core envelope dataclass."""

    def test_wrap_creates_envelope(self):
        env = TelemetryEnvelope.wrap(
            event_type="pedr.search.completed",
            source="pedr",
            payload={"query": "test", "results": 5},
        )
        assert env.event_type == "pedr.search.completed"
        assert env.source == "pedr"
        assert env.payload == {"query": "test", "results": 5}
        assert env.ts  # auto-generated

    def test_wrap_with_sprint_id(self):
        env = TelemetryEnvelope.wrap(
            event_type="quality.gate.evaluation",
            source="quality",
            payload={},
            sprint_id="sprint-35",
        )
        assert env.sprint_id == "sprint-35"

    def test_wrap_with_explicit_ts(self):
        env = TelemetryEnvelope.wrap(
            event_type="test",
            source="tracelab",
            payload={},
            ts="2026-03-12T12:00:00Z",
        )
        assert env.ts == "2026-03-12T12:00:00Z"

    def test_to_dict(self):
        env = TelemetryEnvelope(
            ts="2026-03-12T12:00:00Z",
            event_type="test.event",
            source="tracelab",
            payload={"key": "value"},
        )
        d = env.to_dict()
        assert d == {
            "ts": "2026-03-12T12:00:00Z",
            "event_type": "test.event",
            "source": "tracelab",
            "payload": {"key": "value"},
        }
        assert "sprint_id" not in d

    def test_to_dict_with_sprint_id(self):
        env = TelemetryEnvelope(
            ts="2026-03-12T12:00:00Z",
            event_type="test",
            source="cmos",
            payload={},
            sprint_id="sprint-35",
        )
        d = env.to_dict()
        assert d["sprint_id"] == "sprint-35"

    def test_to_json(self):
        env = TelemetryEnvelope(
            ts="2026-03-12T12:00:00Z",
            event_type="test",
            source="tracelab",
            payload={"n": 42},
        )
        parsed = json.loads(env.to_json())
        assert parsed["event_type"] == "test"
        assert parsed["payload"]["n"] == 42

    def test_from_legacy_extracts_ts(self):
        raw = {"ts": "2026-01-01T00:00:00Z", "model": "gpt-4", "cost": 0.01}
        env = TelemetryEnvelope.from_legacy(
            raw, event_type="cost.event", source="tracelab"
        )
        assert env.ts == "2026-01-01T00:00:00Z"
        assert env.event_type == "cost.event"
        assert env.payload == {"model": "gpt-4", "cost": 0.01}

    def test_from_legacy_extracts_event_type_field(self):
        raw = {
            "ts": "2026-01-01T00:00:00Z",
            "event_type": "pedr.baseline.capture",
            "data": {},
        }
        env = TelemetryEnvelope.from_legacy(raw, source="pedr")
        assert env.event_type == "pedr.baseline.capture"
        assert "event_type" not in env.payload

    def test_from_legacy_extracts_event_field(self):
        raw = {
            "ts": "2026-01-01T00:00:00Z",
            "event": "pedr_graph_telemetry",
            "graph": {},
        }
        env = TelemetryEnvelope.from_legacy(raw, source="pedr")
        assert env.event_type == "pedr_graph_telemetry"

    def test_from_legacy_extracts_type_field(self):
        raw = {"ts": "2026-01-01T00:00:00Z", "type": "latency_sample", "p95": 100}
        env = TelemetryEnvelope.from_legacy(raw, source="tracelab")
        assert env.event_type == "latency_sample"

    def test_from_legacy_missing_ts_uses_default(self):
        raw = {"model": "gpt-4"}
        env = TelemetryEnvelope.from_legacy(raw, event_type="test", source="tracelab")
        assert env.ts  # should be a valid timestamp

    def test_from_legacy_unknown_event_type(self):
        raw = {"ts": "2026-01-01T00:00:00Z", "custom_field": "value"}
        env = TelemetryEnvelope.from_legacy(raw, source="tracelab")
        assert env.event_type == "unknown"


# -------------------------------------------------------------------------
# is_envelope_format tests
# -------------------------------------------------------------------------


class TestIsEnvelopeFormat:
    """Detect whether an event conforms to the envelope schema."""

    def test_valid_envelope(self):
        event = {
            "ts": "2026-01-01T00:00:00Z",
            "event_type": "test",
            "source": "tracelab",
            "payload": {},
        }
        assert is_envelope_format(event) is True

    def test_missing_payload(self):
        event = {
            "ts": "2026-01-01T00:00:00Z",
            "event_type": "test",
            "source": "tracelab",
        }
        assert is_envelope_format(event) is False

    def test_payload_not_dict(self):
        event = {
            "ts": "2026-01-01T00:00:00Z",
            "event_type": "test",
            "source": "tracelab",
            "payload": "not a dict",
        }
        assert is_envelope_format(event) is False

    def test_missing_source(self):
        event = {"ts": "2026-01-01T00:00:00Z", "event_type": "test", "payload": {}}
        assert is_envelope_format(event) is False

    def test_legacy_event_not_envelope(self):
        event = {"ts": "2026-01-01T00:00:00Z", "model": "gpt-4", "cost": 0.01}
        assert is_envelope_format(event) is False

    def test_envelope_with_extra_fields(self):
        event = {
            "ts": "2026-01-01T00:00:00Z",
            "event_type": "test",
            "source": "tracelab",
            "payload": {},
            "sprint_id": "sprint-35",
            "extra": "field",
        }
        assert is_envelope_format(event) is True


# -------------------------------------------------------------------------
# emit_telemetry tests
# -------------------------------------------------------------------------


class TestEmitTelemetry:
    """File-writing telemetry helper."""

    def test_creates_file_and_writes_envelope(self, tmp_path):
        path = tmp_path / "events" / "test.jsonl"
        result = emit_telemetry(
            path=path,
            event_type="test.event",
            source="tracelab",
            payload={"key": "value"},
        )
        assert result is True
        assert path.exists()

        with open(path) as fh:
            line = fh.readline()
            event = json.loads(line)
            assert event["event_type"] == "test.event"
            assert event["source"] == "tracelab"
            assert event["payload"] == {"key": "value"}

    def test_appends_to_existing_file(self, tmp_path):
        path = tmp_path / "test.jsonl"
        emit_telemetry(path=path, event_type="first", source="tracelab", payload={})
        emit_telemetry(path=path, event_type="second", source="tracelab", payload={})

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event_type"] == "first"
        assert json.loads(lines[1])["event_type"] == "second"

    def test_includes_sprint_id(self, tmp_path):
        path = tmp_path / "test.jsonl"
        emit_telemetry(
            path=path,
            event_type="test",
            source="cmos",
            payload={},
            sprint_id="sprint-35",
        )

        event = json.loads(path.read_text().strip())
        assert event["sprint_id"] == "sprint-35"

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "events.jsonl"
        emit_telemetry(path=path, event_type="test", source="tracelab", payload={})
        assert path.exists()

    def test_returns_false_on_write_failure(self, tmp_path):
        path = tmp_path / "readonly"
        path.mkdir()
        result = emit_telemetry(
            path=path,  # directory, not a file
            event_type="test",
            source="tracelab",
            payload={},
        )
        assert result is False


# -------------------------------------------------------------------------
# validate_jsonl_file tests
# -------------------------------------------------------------------------


class TestValidateJsonlFile:
    """JSONL conformance validation."""

    def test_valid_file(self, tmp_path):
        path = tmp_path / "valid.jsonl"
        emit_telemetry(
            path=path, event_type="test", source="tracelab", payload={"a": 1}
        )
        emit_telemetry(
            path=path, event_type="test", source="tracelab", payload={"b": 2}
        )

        result = validate_jsonl_file(path)
        assert result["total"] == 2
        assert result["conforming"] == 2
        assert result["violations"] == 0
        assert result["conformance_rate"] == 1.0

    def test_legacy_file(self, tmp_path):
        path = tmp_path / "legacy.jsonl"
        with open(path, "w") as fh:
            fh.write(json.dumps({"ts": "2026-01-01", "model": "gpt-4"}) + "\n")

        result = validate_jsonl_file(path)
        assert result["total"] == 1
        assert result["conforming"] == 0
        assert result["violations"] == 1
        assert result["first_violations"][0]["error"] == "missing envelope fields"

    def test_mixed_file(self, tmp_path):
        path = tmp_path / "mixed.jsonl"
        emit_telemetry(path=path, event_type="test", source="tracelab", payload={})
        with open(path, "a") as fh:
            fh.write(json.dumps({"ts": "2026-01-01", "old": True}) + "\n")

        result = validate_jsonl_file(path)
        assert result["total"] == 2
        assert result["conforming"] == 1
        assert result["violations"] == 1

    def test_nonexistent_file(self, tmp_path):
        result = validate_jsonl_file(tmp_path / "nope.jsonl")
        assert result["exists"] is False

    def test_invalid_json_line(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        with open(path, "w") as fh:
            fh.write("{invalid json\n")

        result = validate_jsonl_file(path)
        assert result["violations"] == 1
        assert result["first_violations"][0]["error"] == "invalid JSON"

    def test_empty_file(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        result = validate_jsonl_file(path)
        assert result["total"] == 0
        assert result["conformance_rate"] == 1.0


# -------------------------------------------------------------------------
# Migration script tests
# -------------------------------------------------------------------------


class TestMigrationScript:
    """Tests for the migration script's line-level logic."""

    def test_migrate_legacy_line(self, tmp_path):
        from scripts.migrate_telemetry_format import migrate_line

        filepath = tmp_path / "quality-automation.jsonl"
        legacy = json.dumps(
            {"ts": "2026-01-01T00:00:00Z", "check_type": "bias", "status": "passed"}
        )
        result = migrate_line(legacy, filepath)
        parsed = json.loads(result)

        assert is_envelope_format(parsed)
        assert parsed["source"] == "quality"
        assert parsed["payload"]["check_type"] == "bias"

    def test_migrate_already_migrated_line(self, tmp_path):
        from scripts.migrate_telemetry_format import migrate_line

        filepath = tmp_path / "test.jsonl"
        envelope = json.dumps(
            {
                "ts": "2026-01-01T00:00:00Z",
                "event_type": "test",
                "source": "tracelab",
                "payload": {},
            }
        )
        result = migrate_line(envelope, filepath)
        assert result == envelope

    def test_migrate_file_creates_backup(self, tmp_path):
        from scripts.migrate_telemetry_format import migrate_file

        path = tmp_path / "quality-gates.jsonl"
        with open(path, "w") as fh:
            fh.write(
                json.dumps({"ts": "2026-01-01", "gate": "test", "status": "pass"})
                + "\n"
            )

        stats = migrate_file(path, apply=True)
        assert stats["migrated"] == 1
        assert (path.with_suffix(".jsonl.pre-migration")).exists()

        with open(path) as fh:
            event = json.loads(fh.readline())
            assert is_envelope_format(event)

    def test_migrate_file_dry_run(self, tmp_path):
        from scripts.migrate_telemetry_format import migrate_file

        path = tmp_path / "test.jsonl"
        original = json.dumps({"ts": "2026-01-01", "old": True})
        with open(path, "w") as fh:
            fh.write(original + "\n")

        stats = migrate_file(path, apply=False)
        assert stats["migrated"] == 1

        # File should be unchanged
        with open(path) as fh:
            assert fh.readline().strip() == original

    def test_migrate_file_idempotent(self, tmp_path):
        from scripts.migrate_telemetry_format import migrate_file

        path = tmp_path / "test.jsonl"
        emit_telemetry(
            path=path, event_type="test", source="tracelab", payload={"x": 1}
        )

        stats = migrate_file(path, apply=True)
        assert stats["migrated"] == 0
        assert stats["already_migrated"] == 1

    def test_sprint_id_extracted_from_filename(self, tmp_path):
        from scripts.migrate_telemetry_format import migrate_line

        filepath = tmp_path / "sprint-26-graph-telemetry.jsonl"
        legacy = json.dumps(
            {"ts": "2026-01-01", "event": "pedr_graph_telemetry", "graph": {}}
        )
        result = migrate_line(legacy, filepath)
        parsed = json.loads(result)

        assert parsed["sprint_id"] == "sprint-26"
