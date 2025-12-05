"""PEDR (Protocol-Enhanced Deep Research) helpers."""

from .quality_scoring import (
    QualityFilters,
    QualityScore,
    QualityScoringService,
    get_quality_scoring_service,
)
from .manifest_transformer import (
    PEDRManifest,
    TransformationResult,
    ManifestTransformer,
    get_manifest_transformer,
)
from .delta_sync import (
    EntityType,
    SyncMode,
    SyncResult,
    ParityCheckResult,
    DeltaSyncService,
    get_delta_sync_service,
)
from .sync_events import (
    SyncEventType,
    SyncEvent,
    SyncEventEmitter,
    emit_mission_completed,
    emit_mission_updated,
    emit_document_processed,
    emit_batch_sync_requested,
    get_sync_event_emitter,
)
from .preflight import (
    PreflightThresholds,
    PreflightService,
    get_preflight_service,
)

__all__ = [
    # Quality scoring
    "QualityFilters",
    "QualityScore",
    "QualityScoringService",
    "get_quality_scoring_service",
    # Manifest transformation
    "PEDRManifest",
    "TransformationResult",
    "ManifestTransformer",
    "get_manifest_transformer",
    # Delta sync
    "EntityType",
    "SyncMode",
    "SyncResult",
    "ParityCheckResult",
    "DeltaSyncService",
    "get_delta_sync_service",
    # Sync events
    "SyncEventType",
    "SyncEvent",
    "SyncEventEmitter",
    "emit_mission_completed",
    "emit_mission_updated",
    "emit_document_processed",
    "emit_batch_sync_requested",
    "get_sync_event_emitter",
    # Pre-flight queries
    "PreflightThresholds",
    "PreflightService",
    "get_preflight_service",
]
