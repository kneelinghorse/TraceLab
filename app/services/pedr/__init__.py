"""PEDR (Protocol-Enhanced Deep Research) helpers."""

from .delta_sync import (
    DeltaSyncService,
    EntityType,
    ParityCheckResult,
    SyncMode,
    SyncResult,
    get_delta_sync_service,
)
from .edge_materialization import (
    EdgeMaterializationService,
    MaterializationResult,
)
from .fusion import (
    RRF_K,
    FusedResult,
    FusionOutput,
    LayerResult,
    RRFConfig,
    RRFFusion,
    get_rrf_fusion,
    rrf_score,
)
from .graph_layer import (
    GraphLayerConfig,
    GraphLayerService,
    URNParser,
)
from .graph_rag import (
    GraphNode,
    GraphRAGHelper,
    GraphSubgraph,
)
from .hybrid_rerank import (
    HybridReranker,
    HybridRerankResult,
    HybridRerankTimings,
    RerankMode,
    get_hybrid_reranker,
)
from .manifest_transformer import (
    ManifestTransformer,
    PEDRManifest,
    TransformationResult,
    get_manifest_transformer,
)
from .pragmatic import (
    IntentDetectionResult,
    PragmaticFilters,
    PragmaticService,
    QueryIntent,
    get_pragmatic_service,
)
from .preflight import (
    PreflightService,
    PreflightThresholds,
    get_preflight_service,
)
from .quality_scoring import (
    QualityFilters,
    QualityScore,
    QualityScoringService,
    get_quality_scoring_service,
)
from .relational import (
    EntityType as RelationalEntityType,
)
from .relational import (
    GraphExpansionResult,
    RelatedEntity,
    RelationalService,
    RelationType,
    get_relational_service,
)
from .search_orchestrator import (
    DEFAULT_LAYER_WEIGHTS,
    LayerTimings,
    PEDRConfig,
    PEDRMetadata,
    PEDRSearchOrchestrator,
    PEDRSearchResponse,
    PEDRSearchResult,
    create_pedr_orchestrator,
    get_pedr_orchestrator,
)
from .semantic_protocol import (
    CONFIDENCE_PRIOR,
    CRITICALITY_WEIGHTS,
    PROTOCOL_VERSION,
    URN,
    ConfidenceScorer,
    CriticalityCalculator,
    ElementMetadata,
    GovernanceMetadata,
    IntentResolver,
    ProtocolManifest,
    SemanticFeatures,
    SemanticIntent,
    SemanticProtocol,
    SemanticVectorGenerator,
    URNGenerator,
    get_semantic_protocol,
)
from .semantic_protocol import (
    EntityType as SemanticEntityType,
)
from .sync_events import (
    SyncEvent,
    SyncEventEmitter,
    SyncEventType,
    emit_batch_sync_requested,
    emit_document_processed,
    emit_mission_completed,
    emit_mission_updated,
    get_sync_event_emitter,
)
from .syntactic import (
    ElementType as SyntacticElementType,
)
from .syntactic import (
    SyntacticFilters,
    SyntacticService,
    TypeDetectionResult,
    get_syntactic_service,
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
    # Hybrid Rerank (B19.4)
    "RerankMode",
    "HybridRerankTimings",
    "HybridRerankResult",
    "HybridReranker",
    "get_hybrid_reranker",
    # Edge materialization
    "EdgeMaterializationService",
    "MaterializationResult",
    # Graph layer
    "GraphLayerConfig",
    "GraphLayerService",
    "URNParser",
    # Graph RAG helper
    "GraphNode",
    "GraphSubgraph",
    "GraphRAGHelper",
]
