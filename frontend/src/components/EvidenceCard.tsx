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
    <article className="rounded-2xl border border-line bg-surface p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-muted">
            Evidence {typeof index === "number" ? index + 1 : ""}
          </p>
          <p className="text-base font-semibold text-foreground">{evidence.source || "Semantic search chunk"}</p>
        </div>
        {relevanceLabel && <span className="text-sm font-medium text-secondary">{relevanceLabel}</span>}
      </div>
      <p className="mt-2 text-sm leading-relaxed text-secondary whitespace-pre-line">{evidence.summary}</p>
      <dl className="mt-3 grid gap-2 text-xs text-muted sm:grid-cols-3">
        {evidence.chunk_id && (
          <div>
            <dt className="font-semibold uppercase tracking-[0.25em]">Chunk</dt>
            <dd className="mt-1 font-mono text-secondary">{evidence.chunk_id}</dd>
          </div>
        )}
        {evidence.insight_id && (
          <div>
            <dt className="font-semibold uppercase tracking-[0.25em]">Insight</dt>
            <dd className="mt-1 font-mono text-secondary">{evidence.insight_id}</dd>
          </div>
        )}
        {evidence.source_type && (
          <div>
            <dt className="font-semibold uppercase tracking-[0.25em]">Source</dt>
            <dd className="mt-1 text-secondary">{evidence.source_type}</dd>
          </div>
        )}
      </dl>
      {evidence.tags?.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {evidence.tags.map((tag) => (
            <span key={tag} className="rounded-full bg-surface px-3 py-1 text-xs font-medium text-secondary">
              {tag}
            </span>
          ))}
        </div>
      ) : null}
    </article>
  );
}
