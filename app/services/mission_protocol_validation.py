"""Helpers for Mission Protocol validation workflows."""
from __future__ import annotations

from typing import Any, Dict, Literal, Sequence

import yaml

from app.models.mission_protocol import (
    MissionProtocolComplete,
    MissionProtocolDraft,
)

MissionState = Literal["draft", "complete"]

_DRAFT_SCHEMA = MissionProtocolDraft.model_json_schema()
_COMPLETE_SCHEMA = MissionProtocolComplete.model_json_schema()
_DRAFT_REQUIRED_FIELDS: tuple[str, ...] = tuple(_DRAFT_SCHEMA.get("required", ()))
_COMPLETE_REQUIRED_FIELDS: tuple[str, ...] = tuple(_COMPLETE_SCHEMA.get("required", ()))
_COMPLETE_ONLY_FIELDS: tuple[str, ...] = tuple(
    field for field in _COMPLETE_REQUIRED_FIELDS if field not in _DRAFT_REQUIRED_FIELDS
)


def parse_mission_yaml(yaml_text: str) -> MissionProtocolDraft:
    """Parse YAML text into a MissionProtocolDraft instance."""
    if not yaml_text.strip():
        raise ValueError("Mission Protocol YAML content cannot be empty.")
    payload = yaml.safe_load(yaml_text)
    if not isinstance(payload, dict):
        raise ValueError("Mission Protocol YAML must represent an object.")
    return MissionProtocolDraft.model_validate(payload)


def validate_mission_payload(
    payload: Dict[str, Any],
    *,
    state: MissionState = "draft",
) -> MissionProtocolDraft | MissionProtocolComplete:
    """Validate a Mission Protocol payload for the requested lifecycle state."""
    model = MissionProtocolDraft if state == "draft" else MissionProtocolComplete
    return model.model_validate(payload)


def promote_to_complete(
    payload: MissionProtocolDraft | Dict[str, Any]
) -> MissionProtocolComplete:
    """Promote a draft payload (or raw dict) to a complete payload."""
    if isinstance(payload, MissionProtocolDraft):
        data = payload.model_dump()
    else:
        data = dict(payload)
    if data.get("status") not in ("complete", "review"):
        data["status"] = "complete"
    return MissionProtocolComplete.model_validate(data)


def mission_protocol_schema(state: MissionState = "draft") -> Dict[str, Any]:
    """Return the JSON Schema for the requested mission protocol state."""
    return MissionProtocolDraft.model_json_schema() if state == "draft" else MissionProtocolComplete.model_json_schema()


def _array_literal(fields: Sequence[str]) -> str:
    if not fields:
        return "ARRAY[]::text[]"
    inner = ", ".join(f"'{field}'" for field in fields)
    return f"ARRAY[{inner}]::text[]"


def build_mission_data_check_constraint(
    *,
    backend: Literal["postgresql", "sqlite"] = "postgresql",
) -> str:
    """Generate the SQL expression that enforces structural JSON rules for missions."""
    if backend == "sqlite":
        return _build_sqlite_constraint()
    return _build_postgres_constraint()


def _build_postgres_constraint() -> str:
    jsonb_mission = "(mission_data)::jsonb"
    clauses: list[str] = [f"jsonb_typeof({jsonb_mission}) = 'object'"]

    if _DRAFT_REQUIRED_FIELDS:
        clauses.append(f"{jsonb_mission} ?& {_array_literal(_DRAFT_REQUIRED_FIELDS)}")

    if _COMPLETE_ONLY_FIELDS:
        clauses.append(
            "("
            f"coalesce({jsonb_mission}->>'status', 'draft') NOT IN ('complete', 'review') "
            f"OR {jsonb_mission} ?& {_array_literal(_COMPLETE_ONLY_FIELDS)}"
            ")"
        )

    clauses.append(
        "("
        f"coalesce({jsonb_mission}->>'status', 'draft') NOT IN ('complete', 'review') "
        f"OR COALESCE(jsonb_typeof({jsonb_mission}->'research_statement') = 'object', FALSE)"
        ")"
    )
    clauses.append(
        "("
        f"coalesce({jsonb_mission}->>'status', 'draft') NOT IN ('complete', 'review') "
        f"OR COALESCE(jsonb_typeof({jsonb_mission}->'synthesis') = 'object', FALSE)"
        ")"
    )
    clauses.append(
        "("
        f"coalesce({jsonb_mission}->>'status', 'draft') NOT IN ('complete', 'review') "
        f"OR jsonb_array_length(COALESCE({jsonb_mission}->'evidence', '[]'::jsonb)) >= 1"
        ")"
    )
    clauses.append(
        "("
        f"coalesce({jsonb_mission}->>'status', 'draft') NOT IN ('complete', 'review') "
        f"OR jsonb_array_length(COALESCE({jsonb_mission}->'key_questions', '[]'::jsonb)) >= 1"
        ")"
    )
    clauses.append(
        "("
        f"coalesce({jsonb_mission}->>'status', 'draft') NOT IN ('complete', 'review') "
        f"OR jsonb_array_length(COALESCE({jsonb_mission}->'quality_checkpoints', '[]'::jsonb)) >= 1"
        ")"
    )
    return " AND ".join(f"({clause})" for clause in clauses)


_SQLITE_COMPLETE_EXPR = (
    "COALESCE(json_extract(mission_data, '$.status'), '\"draft\"') "
    "IN ('\"complete\"','\"review\"')"
)


def _build_sqlite_constraint() -> str:
    clauses = [
        "json_valid(mission_data)",
        "json_type(mission_data, '$') = 'object'",
    ]

    for field in _DRAFT_REQUIRED_FIELDS:
        clauses.append(f"json_type(mission_data, '$.{field}') IS NOT NULL")

    if _COMPLETE_ONLY_FIELDS:
        required_checks = " AND ".join(
            f"json_type(mission_data, '$.{field}') IS NOT NULL"
            for field in _COMPLETE_ONLY_FIELDS
        )
        clauses.append(f"(NOT {_SQLITE_COMPLETE_EXPR} OR ({required_checks}))")

    clauses.append(
        "("
        f"NOT {_SQLITE_COMPLETE_EXPR} "
        "OR json_type(mission_data, '$.research_statement') = 'object'"
        ")"
    )
    clauses.append(
        "("
        f"NOT {_SQLITE_COMPLETE_EXPR} "
        "OR json_type(mission_data, '$.synthesis') = 'object'"
        ")"
    )
    clauses.append(
        "("
        f"NOT {_SQLITE_COMPLETE_EXPR} "
        "OR json_array_length(COALESCE(json_extract(mission_data, '$.evidence'), json('[]'))) >= 1"
        ")"
    )
    clauses.append(
        "("
        f"NOT {_SQLITE_COMPLETE_EXPR} "
        "OR json_array_length(COALESCE(json_extract(mission_data, '$.key_questions'), json('[]'))) >= 1"
        ")"
    )
    clauses.append(
        "("
        f"NOT {_SQLITE_COMPLETE_EXPR} "
        "OR json_array_length(COALESCE(json_extract(mission_data, '$.quality_checkpoints'), json('[]'))) >= 1"
        ")"
    )
    return " AND ".join(f"({clause})" for clause in clauses)
