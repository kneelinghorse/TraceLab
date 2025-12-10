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
from .syntactic import (
    ElementType as SyntacticElementType,
    TypeDetectionResult,
    SyntacticFilters,
    SyntacticService,
    get_syntactic_service,
)
from .pragmatic import (
    QueryIntent,
    IntentDetectionResult,
    PragmaticFilters,
    PragmaticService,
    get_pragmatic_service,
)
from .semantic_protocol import (
    URN,
    URNGenerator,
    GovernanceMetadata,
    SemanticFeatures,
    ElementMetadata,
    ProtocolManifest,
    ConfidenceScorer,
    CriticalityCalculator,
    IntentResolver,
    SemanticVectorGenerator,
    SemanticProtocol,
    get_semantic_protocol,
    EntityType as SemanticEntityType,
    SemanticIntent,
    PROTOCOL_VERSION,
    CRITICALITY_WEIGHTS,
    CONFIDENCE_PRIOR,
)
from .fusion import (
    RRFConfig,
    LayerResult,
    FusedResult,
    FusionOutput,
    RRFFusion,
    get_rrf_fusion,
    rrf_score,
    RRF_K,
)
from .search_orchestrator import (
    PEDRConfig,
    LayerTimings,
    PEDRMetadata,
    PEDRSearchResult,
    PEDRSearchResponse,
    PEDRSearchOrchestrator,
    get_pedr_orchestrator,
    create_pedr_orchestrator,
    DEFAULT_LAYER_WEIGHTS,
)
from .relational import (
    RelationType,
    EntityType as RelationalEntityType,
    RelatedEntity,
    GraphExpansionResult,
    RelationalService,
    get_relational_service,
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
    # Syntactic layer (type detection + filtering)
    "SyntacticElementType",
    "TypeDetectionResult",
    "SyntacticFilters",
    "SyntacticService",
    "get_syntactic_service",
    # Pragmatic layer (intent classification)
    "QueryIntent",
    "IntentDetectionResult",
    "PragmaticFilters",
    "PragmaticService",
    "get_pragmatic_service",
    # Semantic Protocol (The Namer)
    "URN",
    "URNGenerator",
    "GovernanceMetadata",
    "SemanticFeatures",
    "ElementMetadata",
    "ProtocolManifest",
    "ConfidenceScorer",
    "CriticalityCalculator",
    "IntentResolver",
    "SemanticVectorGenerator",
    "SemanticProtocol",
    "get_semantic_protocol",
    "SemanticEntityType",
    "SemanticIntent",
    "PROTOCOL_VERSION",
    "CRITICALITY_WEIGHTS",
    "CONFIDENCE_PRIOR",
    # RRF Fusion
    "RRFConfig",
    "LayerResult",
    "FusedResult",
    "FusionOutput",
    "RRFFusion",
    "get_rrf_fusion",
    "rrf_score",
    "RRF_K",
    # Search Orchestrator
    "PEDRConfig",
    "LayerTimings",
    "PEDRMetadata",
    "PEDRSearchResult",
    "PEDRSearchResponse",
    "PEDRSearchOrchestrator",
    "get_pedr_orchestrator",
    "create_pedr_orchestrator",
    "DEFAULT_LAYER_WEIGHTS",
    # Relational Layer (Graph Context)
    "RelationType",
    "RelationalEntityType",
    "RelatedEntity",
    "GraphExpansionResult",
    "RelationalService",
    "get_relational_service",
]
