"""Utilities for translating Pydantic validation errors into API responses."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError


def _format_field_path(path: Sequence[Any]) -> str:
    """Convert a tuple/list location into a dotted path string."""
    return ".".join(str(part) for part in path)


def extract_validation_errors(error: ValidationError) -> list[dict[str, Any]]:
    """Return a serialisable list of validation issues."""
    details: list[dict[str, Any]] = []
    for issue in error.errors():
        details.append(
            {
                "field": _format_field_path(issue.get("loc", ())),
                "message": issue.get("msg", ""),
                "type": issue.get("type", ""),
                "context": issue.get("ctx") or {},
            }
        )
    return details


def transform_validation_error(
    error: ValidationError, *, summary: str | None = None, next_hint: str | None = None
) -> dict[str, Any]:
    """Produce a structured API payload for validation failures."""
    return {
        "error": "validation_error",
        "summary": summary or "Payload validation failed.",
        "details": extract_validation_errors(error),
        "next_hint": next_hint,
    }
