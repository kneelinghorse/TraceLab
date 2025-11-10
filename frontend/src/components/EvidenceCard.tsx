import type { Evidence } from "@/types/mission";

type EvidenceCardProps = {
  evidence: Evidence;
  index?: number;
};

const formatScore = (score?: number | null) => {
  if (typeof score !== "number" || Number.isNaN(score)) {
    return null;
  }
  return `${(score * 100).toFixed(0)}% relevance`;
};

export function EvidenceCard({ evidence, index }: EvidenceCardProps) {
  const relevanceLabel = formatScore(evidence.relevance_score);
  return (
    <article className="rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">
            Evidence {typeof index === "number" ? index + 1 : ""}
          </p>
          <p className="text-base font-semibold text-slate-900">{evidence.source || "Semantic search chunk"}</p>
        </div>
        {relevanceLabel && <span className="text-sm font-medium text-slate-600">{relevanceLabel}</span>}
      </div>
      <p className="mt-2 text-sm leading-relaxed text-slate-700 whitespace-pre-line">{evidence.summary}</p>
      <dl className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-3">
        {evidence.chunk_id && (
          <div>
            <dt className="font-semibold uppercase tracking-[0.25em]">Chunk</dt>
            <dd className="mt-1 font-mono text-slate-700">{evidence.chunk_id}</dd>
          </div>
        )}
        {evidence.insight_id && (
          <div>
            <dt className="font-semibold uppercase tracking-[0.25em]">Insight</dt>
            <dd className="mt-1 font-mono text-slate-700">{evidence.insight_id}</dd>
          </div>
        )}
        {evidence.source_type && (
          <div>
            <dt className="font-semibold uppercase tracking-[0.25em]">Source</dt>
            <dd className="mt-1 text-slate-700">{evidence.source_type}</dd>
          </div>
        )}
      </dl>
      {evidence.tags?.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {evidence.tags.map((tag) => (
            <span key={tag} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
              {tag}
            </span>
          ))}
        </div>
      ) : null}
    </article>
  );
}
