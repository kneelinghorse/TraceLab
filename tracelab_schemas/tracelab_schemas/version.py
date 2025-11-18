"""Package version metadata for tracelab-schemas."""

from __future__ import annotations

__all__ = ["__version__", "get_version"]

__version__ = "1.0.0"


def get_version() -> str:
    """Return the canonical package version."""
    return __version__
