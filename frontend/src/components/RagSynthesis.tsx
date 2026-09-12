import clsx from "clsx";

import type { RagCitation, RagResponsePayload } from "@/types/search";

type RagSynthesisProps = {
  payload: RagResponsePayload | null;
  isLoading: boolean;
  error?: string | null;
  onCitationClick?: (citation: RagCitation, index: number) => void;
};

export function RagSynthesis({ payload, isLoading, error, onCitationClick }: RagSynthesisProps) {
  return (
    <section className="panel h-full p-6 space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-secondary">RAG Answer</p>
        <h2 className="text-2xl font-semibold text-foreground">Synthesized response with citations</h2>
      </div>

      {error && <p className="rounded-xl border border-danger-line bg-danger-surface px-4 py-3 text-danger">{error}</p>}

      {isLoading && (
        <div className="flex items-center gap-3 rounded-xl border border-line bg-surface-alt px-4 py-3 text-sm text-secondary">
          <span className="h-3 w-3 animate-spin rounded-full border-2 border-line border-t-transparent" />
          Generating answer…
        </div>
      )}

      {payload ? (
        <div className="space-y-5">
          <article className="rounded-2xl border border-line bg-surface-alt p-5">
            <p className="text-sm text-secondary whitespace-pre-line leading-relaxed">{payload.answer}</p>
          </article>

          <div className="grid gap-4 md:grid-cols-2">
            <Metric label="Latency" value={`${payload.latency_ms.toFixed(0)} ms`} />
            <Metric
              label="Quality"
              value={`${(payload.quality.composite_score * 100).toFixed(1)} / ${(payload.quality.threshold * 100).toFixed(0)}`}
              muted={payload.quality.composite_score < payload.quality.threshold}
            />
            <Metric label="Model" value={payload.routing.selected_model} />
            <Metric label="Cache" value={payload.cache.hit ? "HIT" : "MISS"} muted={!payload.cache.hit} />
          </div>

          <div className="space-y-3">
            <p className="text-xs uppercase tracking-[0.3em] text-secondary">Citations</p>
            {payload.citations.length === 0 ? (
              <p className="text-sm text-secondary">No citations returned.</p>
            ) : (
              <ol className="space-y-3">
                {payload.citations.map((citation, index) => (
                  <li key={`${citation.chunk_id ?? index}`} className="rounded-2xl border border-line bg-background p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm text-secondary">
                          <span className="font-semibold text-accent-text">[{index + 1}]</span> {citation.document_id ?? "Unknown doc"}
                        </p>
                        {citation.snippet && <p className="mt-2 text-sm text-secondary">{citation.snippet}</p>}
                        <p className="mt-1 text-xs text-secondary">
                          Chunk {citation.chunk_index ?? citation.chunk_id ?? "?"} · Score {citation.score?.toFixed(3) ?? "–"}
                        </p>
                      </div>
                      {onCitationClick && citation.chunk_id && (
                        <button
                          type="button"
                          onClick={() => onCitationClick(citation, index)}
                          className="text-xs font-semibold text-accent-text hover:text-accent-text"
                        >
                          Focus result
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      ) : (
        !isLoading && <p className="text-sm text-secondary">Run a search to generate an answer.</p>
      )}
    </section>
  );
}

type MetricProps = {
  label: string;
  value: string;
  muted?: boolean;
};

function Metric({ label, value, muted = false }: MetricProps) {
  return (
    <div
      className={clsx(
        "rounded-2xl border px-4 py-3",
        muted ? "border-line bg-surface-alt text-secondary" : "border-line bg-surface text-foreground",
      )}
    >
      <p className="text-xs uppercase tracking-[0.3em] text-secondary">{label}</p>
      <p className="text-lg font-semibold">{value}</p>
    </div>
  );
}
