"""PEDR-specific exception hierarchy.

Provides structured error types for each PEDR search layer so failures
can be diagnosed precisely rather than caught as generic Exception.
"""
from __future__ import annotations

from typing import Optional


class PEDRError(Exception):
    """Base exception for all PEDR pipeline errors."""

    def __init__(self, message: str, *, layer: Optional[str] = None) -> None:
        self.layer = layer
        super().__init__(message)


# ---------------------------------------------------------------------------
# Retrieval layer errors
# ---------------------------------------------------------------------------

class LexicalSearchError(PEDRError):
    """Failure in the lexical (PostgreSQL full-text) search layer."""

    def __init__(self, message: str) -> None:
        super().__init__(message, layer="lexical")


class SemanticSearchError(PEDRError):
    """Failure in the semantic (Qdrant vector) search layer."""

    def __init__(self, message: str) -> None:
        super().__init__(message, layer="semantic")


class GraphLayerError(PEDRError):
    """Failure in the graph expansion layer."""

    def __init__(self, message: str) -> None:
        super().__init__(message, layer="graph")


# ---------------------------------------------------------------------------
# Post-processing layer errors
# ---------------------------------------------------------------------------

class SyntacticLayerError(PEDRError):
    """Failure in the syntactic (type detection / filtering) layer."""

    def __init__(self, message: str) -> None:
        super().__init__(message, layer="syntactic")


class PragmaticLayerError(PEDRError):
    """Failure in the pragmatic (intent classification) layer."""

    def __init__(self, message: str) -> None:
        super().__init__(message, layer="pragmatic")


class GovernanceLayerError(PEDRError):
    """Failure in the governance (quality scoring / PII) layer."""

    def __init__(self, message: str) -> None:
        super().__init__(message, layer="governance")


# ---------------------------------------------------------------------------
# Fusion / pipeline errors
# ---------------------------------------------------------------------------

class FusionError(PEDRError):
    """Failure during RRF fusion of layer results."""

    def __init__(self, message: str) -> None:
        super().__init__(message, layer="fusion")


__all__ = [
    "PEDRError",
    "LexicalSearchError",
    "SemanticSearchError",
    "GraphLayerError",
    "SyntacticLayerError",
    "PragmaticLayerError",
    "GovernanceLayerError",
    "FusionError",
]
