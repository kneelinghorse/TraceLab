import type { ApiMission } from "@/types/mission";
import { z } from "zod";

const object = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const qualitySchema = z.object({
  schema_version: z.number().optional(),
  delivery_quality: z.string().optional(),
  verification: z.object({ version: z.number(), scope: z.string(), report_wide_accuracy: z.string() }).passthrough().optional(),
}).passthrough();

function qualityData(mission: ApiMission) {
  const execution = object(mission.execution_metadata);
  const forensic = object(mission.result_protocol?.report_metadata?.forensic);
  const raw = execution.quality_record ?? forensic.quality_record ?? null;
  const parsed = qualitySchema.safeParse(raw);
  const quality = parsed.success ? parsed.data : null;
  const outcome = object(execution.final_outcome);
  const delivery = [outcome.delivery_quality, execution.delivery_quality, quality?.delivery_quality]
    .find((value): value is string => typeof value === "string" && value.length > 0);
  const reasons = [outcome.quality_gate_failures, outcome.coverage_gate_failures, outcome.structural_validation_failures,
    execution.quality_gate_failures, execution.coverage_gate_failures, execution.structural_validation_failures]
    .flatMap(value => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []);
  return { raw, quality, delivery, reasons: [...new Set(reasons)] };
}

/** Translate actionable codes without treating sample or retrieval counts as accuracy. */
export function qualityReason(value: string): string {
  const count = /^(critique_unassessed_claims|critique_contradicted|missing_cited_sources|cited_without_readable_body|truncated_cited_bodies|unresolved_cited_fetch_failures)_(\d+)$/.exec(value);
  if (count) {
    const [, code, n] = count;
    if (code === "critique_unassessed_claims") return `${n} claim${n === "1" ? " was" : "s were"} not assessed.`;
    if (code === "critique_contradicted") return `${n} assessed claim${n === "1" ? " was" : "s were"} contradicted.`;
    if (code === "missing_cited_sources") return `${n} cited source${n === "1" ? " is" : "s are"} missing.`;
    if (code === "truncated_cited_bodies") return `${n} cited source bod${n === "1" ? "y was" : "ies were"} truncated.`;
    if (code === "unresolved_cited_fetch_failures") return `${n} cited source fetch${n === "1" ? " remains" : "es remain"} unresolved.`;
    return `${n} cited source${n === "1" ? " has" : "s have"} no readable body.`;
  }
  if (value === "critique_assessment_unknown") return "Claim assessment is unavailable or incomplete.";
  if (value === "retrieval_dependency_attribution_unknown") return "The effect of retrieval failures on cited evidence is unknown.";
  if (value === "retrieval_failure_impact_unknown") return "The impact of earlier retrieval failures is unknown.";
  return "Additional quality issue reported; see Raw quality data in Details.";
}

const labels: Record<string, string> = {
  clean: "No detected material issue",
  usable_with_warning: "Usable with warnings",
  degraded: "Degraded result",
  failed: "Failed quality checks",
};
const labelFor = (values: Record<string, string>, key: unknown) => typeof key === "string" && Object.prototype.hasOwnProperty.call(values, key) ? values[key] : undefined;

export function MissionQualitySummary({ mission }: { mission: ApiMission }) {
  const { quality, delivery, reasons } = qualityData(mission);
  const assessed = (quality?.schema_version ?? 0) >= 5 && quality?.verification?.version === 1;
  const label = assessed ? labelFor(labels, delivery) ?? "Quality outcome unknown" : "Quality not assessed for this run";
  const explanations = [...new Set(reasons.map(qualityReason))];
  return <section aria-label="Research quality" className="space-y-1 px-4 pt-3 text-sm sm:px-6">
    <p className="font-semibold">{label}</p>
    {assessed && <p className="text-secondary">{quality?.verification?.scope === "sampled" ? "Sampled verification; report-wide accuracy unknown" : "Verification scope unknown; report-wide accuracy unknown"}</p>}
    {explanations.length > 0 && <ul className="list-disc space-y-1 pl-5 text-secondary">{explanations.map(value => <li key={value}>{value}</li>)}</ul>}
  </section>;
}

export function RawQualityData({ mission }: { mission: ApiMission }) {
  const execution = object(mission.execution_metadata);
  const outcome = object(execution.final_outcome);
  const { raw } = qualityData(mission);
  const { attempts, recovery } = failureData(mission);
  const gates = (source: Record<string, unknown>) => ({ delivery_quality: source.delivery_quality, quality_gate_failures: source.quality_gate_failures, coverage_gate_failures: source.coverage_gate_failures, structural_validation_failures: source.structural_validation_failures });
  const data = { quality_record: raw, final_outcome: gates(outcome), execution_metadata: gates(execution), generation_recovery_result: recovery, provider_failures: attempts };
  return <details className="mx-4 mb-4 rounded-lg border border-line p-4 text-sm">
    <summary className="cursor-pointer rounded font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">Raw quality data</summary>
    <p className="mt-3 text-secondary">Recorded verification, retrieval and citation accounting. These counts do not establish report-wide accuracy.</p>
    <pre tabIndex={0} aria-label="Recorded quality and diagnostics" className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap break-all rounded bg-background p-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">{JSON.stringify(data, null, 2)}</pre>
  </details>;
}

function failureData(mission: ApiMission) {
  const telemetry = object(object(mission.execution_metadata).synthesis_telemetry);
  const attempts = (Array.isArray(telemetry.provider_attempts) ? telemetry.provider_attempts : [])
    .map(attempt => object(object(attempt).failure)).filter(failure => Object.keys(failure).length > 0)
    // Only these content-free diagnostics belong in this new surface. Never copy error text.
    .map(failure => ({ rejection: failure.rejection ?? null, request_shape: failure.request_shape ?? null }));
  return { attempts, recovery: telemetry.generation_recovery_result };
}

const rejectionLabels: Record<string, string> = {
  context_limit: "Context limit exceeded",
  unsupported_parameter: "Unsupported parameter",
  unsupported_value: "Unsupported parameter value",
  content_rejection: "Content rejected",
  invalid_json: "Invalid JSON",
  invalid_message_structure: "Invalid message structure",
  unknown: "Unknown rejection subtype",
};
const sourceLabels: Record<string, string> = {
  code: "Provider error code", type: "Provider error type", message_pattern: "Provider message pattern", unknown: "Unknown classification source",
};

export function MissionFailureDetails({ mission }: { mission: ApiMission }) {
  if (!["blocked", "validation_failed"].includes(mission.status)) return null;
  const { attempts, recovery } = failureData(mission);
  if (!attempts.length && (!recovery || recovery === "not_attempted")) return null;
  return <section aria-label="Provider failure details" className="m-4 space-y-3 rounded-lg border border-danger-line bg-danger-surface p-4 text-sm">
    <h2 className="font-semibold">Provider failure details</h2>
    {recovery === "provider_failed" ? <p>Provider failed again during retained-memory finalization.</p>
      : recovery === "unknown_finish" ? <p>Finalization returned a response without a proven finish reason.</p>
      : recovery && recovery !== "not_attempted" ? <p>Finalization outcome unknown.</p> : null}
    {attempts.map((attempt, index) => {
      const rejection = object(attempt.rejection), shape = object(attempt.request_shape);
      const subtype = rejection.version === 1 ? labelFor(rejectionLabels, rejection.subtype) : undefined;
      const source = rejection.version === 1 ? labelFor(sourceLabels, rejection.subtype_source) : undefined;
      return <div key={index} className="space-y-1">
        <p className="font-medium">Failed provider attempt {index + 1}</p>
        <dl><div className="flex flex-wrap gap-x-2"><dt>Rejection:</dt><dd>{subtype ?? "Unknown rejection subtype"}</dd></div>
          <div className="flex flex-wrap gap-x-2"><dt>Classification source:</dt><dd>{source ?? "Unknown classification source"}</dd></div></dl>
        {rejection.subtype_source === "message_pattern" && <p>Classified from provider wording; the root cause is not independently verified.</p>}
        <p>{shape.version !== 1 || typeof shape.available !== "boolean" ? "Request shape availability not recorded." : shape.available ? "Request shape available." : "Request shape unavailable."}</p>
      </div>;
    })}
  </section>;
}
