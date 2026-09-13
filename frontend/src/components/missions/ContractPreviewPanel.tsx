import { useCallback, useState } from "react";

import { missionsApi } from "@/lib/api/missions";
import type { MissionContractPreview } from "@/types/mission";

interface ContractPreviewPanelProps {
  missionId: string;
}

/**
 * Mission contract preview panel (T40.4).
 *
 * Fetches the compiled DeepSearch contract on demand and renders the
 * summary counts + the full payload. Button-triggered rather than
 * live-as-you-edit so each click corresponds to one upstream preview call.
 */
export function ContractPreviewPanel({ missionId }: ContractPreviewPanelProps) {
  const [preview, setPreview] = useState<MissionContractPreview | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await missionsApi.previewContract(missionId);
      setPreview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch preview");
      setPreview(null);
    } finally {
      setIsLoading(false);
    }
  }, [missionId]);

  return (
    <section className="rounded-lg border border-line bg-surface p-6 space-y-4">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground">
            Contract preview
          </h2>
          <p className="text-sm text-muted">
            See the compiled DeepSearch contract — named entities, evidence slots,
            acceptance checks — before submitting.
          </p>
        </div>
        <button
          type="button"
          onClick={handleFetch}
          disabled={isLoading}
          className="px-4 py-2 text-sm font-medium rounded-lg bg-accent text-on-accent hover:bg-accent disabled:opacity-50 transition-colors"
        >
          {isLoading ? "Previewing…" : preview ? "Refresh preview" : "Preview contract"}
        </button>
      </header>

      {error && (
        <div className="p-3 bg-danger-surface border border-danger-line rounded-lg text-sm text-danger">
          {error}
        </div>
      )}

      {preview && (
        <div className="space-y-4">
          <dl className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <PreviewStat label="Named entities" value={preview.named_entities.length} />
            <PreviewStat label="Objectives" value={preview.objectives.length} />
            <PreviewStat label="Evidence slots" value={preview.evidence_slots.length} />
            <PreviewStat label="Acceptance checks" value={preview.acceptance_checks.length} />
            <PreviewStat label="Deliverable schemas" value={preview.deliverable_schemas.length} />
            <PreviewStat
              label="Coverage thresholds"
              value={Object.keys(preview.coverage_thresholds).length}
            />
            <PreviewStat
              label="Validation thresholds"
              value={Object.keys(preview.validation_thresholds).length}
            />
          </dl>

          {preview.named_entities.length > 0 && (
            <PreviewSection title="Named entities">
              <ul className="flex flex-wrap gap-2">
                {preview.named_entities.map((entity) => (
                  <li
                    key={entity}
                    className="px-2.5 py-1 rounded-full bg-info-surface text-info text-xs"
                  >
                    {entity}
                  </li>
                ))}
              </ul>
            </PreviewSection>
          )}

          {preview.deliverable_schemas.length > 0 && (
            <PreviewSection title="Deliverable schemas">
              <pre className="p-3 bg-background rounded-lg text-xs overflow-x-auto">
                {JSON.stringify(preview.deliverable_schemas, null, 2)}
              </pre>
            </PreviewSection>
          )}

          {(preview.coverage_thresholds && Object.keys(preview.coverage_thresholds).length > 0) && (
            <PreviewSection title="Coverage thresholds">
              <pre className="p-3 bg-background rounded-lg text-xs overflow-x-auto">
                {JSON.stringify(preview.coverage_thresholds, null, 2)}
              </pre>
            </PreviewSection>
          )}

          {(preview.validation_thresholds && Object.keys(preview.validation_thresholds).length > 0) && (
            <PreviewSection title="Validation thresholds">
              <pre className="p-3 bg-background rounded-lg text-xs overflow-x-auto">
                {JSON.stringify(preview.validation_thresholds, null, 2)}
              </pre>
            </PreviewSection>
          )}

          <details className="rounded-lg border border-line">
            <summary className="px-3 py-2 cursor-pointer text-sm text-secondary">
              Full compiled contract (raw JSON)
            </summary>
            <pre className="p-3 bg-background text-xs overflow-x-auto">
              {JSON.stringify(preview, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </section>
  );
}

function PreviewStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-background p-3">
      <dt className="text-xs uppercase tracking-wide text-muted">
        {label}
      </dt>
      <dd className="mt-1 text-xl font-semibold text-foreground">
        {value}
      </dd>
    </div>
  );
}

function PreviewSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-secondary mb-2">
        {title}
      </h3>
      {children}
    </div>
  );
}
