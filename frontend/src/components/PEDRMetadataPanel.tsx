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
    <div className={`flex flex-wrap items-center gap-3 text-xs text-slate-400 ${className}`}>
      <span className="flex items-center gap-1">
        <span className="text-slate-500">Intent:</span>
        <span className="text-sky-300">{metadata.intent}</span>
        <span className="text-slate-500">({intentConfidencePercent}%)</span>
      </span>

      {metadata.detected_type && (
        <span className="flex items-center gap-1">
          <span className="text-slate-500">Type:</span>
          <span className="text-emerald-300">{metadata.detected_type}</span>
          <span className="text-slate-500">({typeConfidencePercent}%)</span>
        </span>
      )}

      <span className="flex items-center gap-1">
        <span className="text-slate-500">Latency:</span>
        <span className={metadata.timings.total_ms < 500 ? "text-emerald-300" : "text-amber-300"}>
          {metadata.timings.total_ms.toFixed(0)}ms
        </span>
      </span>

      <span className="flex items-center gap-1">
        <span className="text-slate-500">Layers:</span>
        <span className="text-slate-300">{metadata.layers_used.length}</span>
      </span>

      {metadata.rerank_mode === "hybrid" && (
        <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-sky-300">
          Hybrid
        </span>
      )}

      {metadata.hybrid_fallback_used && (
        <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-300">
          Fallback
        </span>
      )}
    </div>
  );
}
