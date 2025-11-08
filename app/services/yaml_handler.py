"""Utilities for Mission Protocol YAML import/export workflows."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from app.models.mission_protocol import MissionProtocolComplete, MissionProtocolDraft
from app.services.mission_protocol_validation import (
    parse_mission_yaml,
    promote_to_complete,
)


def load_mission_yaml(
    yaml_text: str,
    *,
    promote: bool = False,
) -> MissionProtocolDraft | MissionProtocolComplete:
    """Parse Mission Protocol YAML text and optionally promote to complete payload."""

    draft = parse_mission_yaml(yaml_text)
    return promote_to_complete(draft) if promote else draft


def load_mission_yaml_file(
    path: Path,
    *,
    promote: bool = False,
    encoding: str = "utf-8",
) -> MissionProtocolDraft | MissionProtocolComplete:
    """Read a YAML file from disk and parse it into Mission Protocol payload."""

    text = path.read_text(encoding=encoding)
    return load_mission_yaml(text, promote=promote)


def dump_mission_yaml(payload: MissionProtocolDraft | MissionProtocolComplete | Dict[str, Any]) -> str:
    """Serialise a Mission Protocol payload into YAML text."""

    if isinstance(payload, (MissionProtocolDraft, MissionProtocolComplete)):
        data = payload.model_dump()
    else:
        data = payload
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def dump_mission_yaml_file(
    payload: MissionProtocolDraft | MissionProtocolComplete | Dict[str, Any],
    path: Path,
    *,
    encoding: str = "utf-8",
) -> None:
    """Write Mission Protocol payload to a YAML file on disk."""

    path.write_text(dump_mission_yaml(payload), encoding=encoding)

