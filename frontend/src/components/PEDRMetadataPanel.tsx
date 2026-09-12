import type { PEDRSearchMetadata } from "@/types/search";

interface PEDRMetadataPanelProps {
  metadata: PEDRSearchMetadata | null;
  className?: string;
}

/**
 * Display PEDR search metadata including intent, type detection, and timing.
 */
export function PEDRMetadataPanel({ metadata, className = "" }: PEDRMetadataPanelProps) {
  if (!metadata) return null;

  const intentConfidencePercent = (metadata.intent_confidence * 100).toFixed(0);
  const typeConfidencePercent = (metadata.type_confidence * 100).toFixed(0);

  return (
    <div className={`flex flex-wrap items-center gap-3 text-xs text-muted ${className}`}>
      <span className="flex items-center gap-1">
        <span className="text-muted">Intent:</span>
        <span className="text-accent-text">{metadata.intent}</span>
        <span className="text-muted">({intentConfidencePercent}%)</span>
      </span>

      {metadata.detected_type && (
        <span className="flex items-center gap-1">
          <span className="text-muted">Type:</span>
          <span className="text-success">{metadata.detected_type}</span>
          <span className="text-muted">({typeConfidencePercent}%)</span>
        </span>
      )}

      <span className="flex items-center gap-1">
        <span className="text-muted">Latency:</span>
        <span className={metadata.timings.total_ms < 500 ? "text-success" : "text-warning"}>
          {metadata.timings.total_ms.toFixed(0)}ms
        </span>
      </span>

      <span className="flex items-center gap-1">
        <span className="text-muted">Layers:</span>
        <span className="text-secondary">{metadata.layers_used.length}</span>
      </span>

      {metadata.rerank_mode === "hybrid" && (
        <span className="rounded-full border border-info-line bg-info-surface px-2 py-0.5 text-accent-text">
          Hybrid
        </span>
      )}

      {metadata.hybrid_fallback_used && (
        <span className="rounded-full border border-warning-line bg-warning-surface px-2 py-0.5 text-warning">
          Fallback
        </span>
      )}
    </div>
  );
}
