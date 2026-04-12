"""Mission Protocol schemas import shim.

All canonical Pydantic models now live inside the standalone
`tracelab_schemas` package so TraceLab and DeepSearch share a single source of
truth. This module re-exports those types for backwards compatibility across
the existing application surface.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

PACKAGE_NAME = "tracelab_schemas"


def _import_schema_package() -> ModuleType:
    """Load the schema package, falling back to the source tree for dev/test."""
    try:
        return importlib.import_module(PACKAGE_NAME)
    except ModuleNotFoundError as error:
        package_root = Path(__file__).resolve().parents[1] / "tracelab_schemas"
        if package_root.exists():
            path_str = str(package_root)
            if path_str not in sys.path:
                sys.path.insert(0, path_str)
            return importlib.import_module(PACKAGE_NAME)
        raise error


_schema_pkg = _import_schema_package()

MissionStatus = _schema_pkg.MissionStatus
KeyQuestionStatus = _schema_pkg.KeyQuestionStatus
QualityGateName = _schema_pkg.QualityGateName
QualityGateStatus = _schema_pkg.QualityGateStatus
REQUIRED_COMPLETION_GATES = _schema_pkg.REQUIRED_COMPLETION_GATES

Evidence = _schema_pkg.Evidence
KeyQuestion = _schema_pkg.KeyQuestion
MethodologyDetails = _schema_pkg.MethodologyDetails
MissionProtocolBase = _schema_pkg.MissionProtocolBase
MissionProtocolComplete = _schema_pkg.MissionProtocolComplete
MissionProtocolDraft = _schema_pkg.MissionProtocolDraft
ParticipantSegment = _schema_pkg.ParticipantSegment
QualityCheckpoint = _schema_pkg.QualityCheckpoint
ResearchStatement = _schema_pkg.ResearchStatement
Synthesis = _schema_pkg.Synthesis
__version__ = getattr(_schema_pkg, "__version__", "0.0.0")

__all__: list[str] = [
    "__version__",
    "Evidence",
    "KeyQuestion",
    "KeyQuestionStatus",
    "MethodologyDetails",
    "MissionProtocolBase",
    "MissionProtocolComplete",
    "MissionProtocolDraft",
    "MissionStatus",
    "ParticipantSegment",
    "QualityCheckpoint",
    "QualityGateName",
    "QualityGateStatus",
    "REQUIRED_COMPLETION_GATES",
    "ResearchStatement",
    "Synthesis",
]
