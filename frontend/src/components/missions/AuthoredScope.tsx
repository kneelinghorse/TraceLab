import { z } from "zod";
import type { ApiMission, AuthoredScope } from "@/types/mission";

const count = z.number().int().nonnegative();
const scopeSchema = z.object({
  version: z.literal("authored-scope-v1"), reference_urls: z.array(z.string()),
  restriction: z.enum(["unrestricted", "domains", "exact_pages"]),
  allowed_urls: z.array(z.string()), allowed_domains: z.array(z.string()),
  min_words: count.nullable(), max_words: count.positive().nullable(), max_sources: count.positive().nullable(),
});
const auditSchema = z.object({
  version: z.literal("persisted-scope-v1"), counter_version: z.literal("unicode-whitespace-v1"),
  controlling_surface: z.literal("persisted_report"), verdict: z.enum(["compliant", "partial", "violated"]),
  policy_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  persisted: z.object({ words: count, sha256: z.string().regex(/^[a-f0-9]{64}$/) }),
  consulted_count: count, violations: z.array(z.string()), warnings: z.array(z.string()),
  unavailable: z.array(z.object({ url: z.string(), reason: z.string() })),
});
function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function wordBounds(scope: AuthoredScope): string {
  if (scope.min_words !== null && scope.max_words !== null) return `${scope.min_words}–${scope.max_words} words`;
  if (scope.max_words !== null) return `At most ${scope.max_words} words`;
  if (scope.min_words !== null) return `At least ${scope.min_words} words`;
  return "No parsed word limit";
}

export function PlannedScopeSummary({ scope }: { scope: unknown }) {
  const parsed = scopeSchema.safeParse(scope);
  if (!parsed.success) return <p className="text-sm text-muted">Planned scope unavailable for this preview.</p>;
  const plan = parsed.data;
  const allowed = plan.restriction === "exact_pages" ? plan.allowed_urls : plan.restriction === "domains" ? plan.allowed_domains : [];
  return <section aria-label="Planned scope" className="min-w-0 space-y-2 rounded-lg border border-line bg-background p-4 text-sm">
    <h3 className="font-semibold">Planned scope</h3>
    <p>{wordBounds(plan)} · {plan.max_sources === null ? "No parsed source cap" : `At most ${plan.max_sources} distinct consulted pages`}</p>
    <p className="text-secondary">{plan.restriction === "exact_pages" ? "Only these exact pages are allowed:" : plan.restriction === "domains" ? "Only these domains and their subdomains are allowed:" : "Sources are unrestricted."}</p>
    {allowed.length > 0 && <ul className="list-disc space-y-1 pl-5">{allowed.map(value => <li key={value} className="break-all">{value}</li>)}</ul>}
    {plan.reference_urls.length > 0 && <details><summary className="cursor-pointer rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">Reference seeds ({plan.reference_urls.length})</summary><p className="mt-2 text-muted">Seeds guide research; they do not create a restriction on their own.</p><ul className="mt-1 list-disc space-y-1 pl-5">{plan.reference_urls.map(value => <li key={value} className="break-all">{value}</li>)}</ul></details>}
    <p className="text-muted">This structural preview describes a plan. It does not verify the deployed worker. Other prose remains guidance unless the compiler parses it as a limit.</p>
  </section>;
}
const reasons: Record<string, string> = {
  scope_words_above_maximum: "The saved report exceeds the maximum word count.",
  scope_words_below_minimum: "The saved report is below the minimum word count.",
  scope_consulted_source_limit_exceeded: "The run consulted more source pages than allowed.",
  scope_consulted_source_not_allowed: "The run consulted pages outside the allowed sources.",
  scope_sources_unavailable: "Some requested sources were unavailable.",
};
function reason(value: string) { return reasons[value] ?? value.replaceAll("_", " "); }

export function ScopeOutcomePanel({ mission }: { mission: ApiMission }) {
  const outcome = object(object(mission.execution_metadata).final_outcome);
  const parsed = auditSchema.safeParse(outcome.authored_scope_validation);
  const valid = parsed.success && !(parsed.data.verdict === "compliant" && (parsed.data.violations.length || parsed.data.unavailable.length));
  const snapshot = object(mission.result_protocol?.report_metadata?.forensic?.authored_scope);
  const scope = scopeSchema.safeParse(snapshot.policy);
  const audit = valid && parsed.success ? parsed.data : null;
  const policy = audit && scope.success && snapshot.policy_sha256 === audit.policy_sha256 ? scope.data : null;
  const quality = [outcome.coverage_gate_failures, outcome.quality_gate_failures, outcome.structural_validation_failures]
    .flatMap(value => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []);
  const qualityWarning = ["usable_with_warning", "degraded", "failed"].includes(String(outcome.delivery_quality));
  const tone = audit?.verdict === "violated" ? "border-danger-line bg-danger-surface" : audit?.verdict === "partial" ? "border-warning-line bg-warning-surface" : "border-line bg-surface";
  return <section aria-label="Scope outcome" className={`min-w-0 space-y-3 rounded-lg border p-4 text-sm ${tone}`}>
    <h2 className="text-base font-semibold">{!audit ? "Scope outcome unknown" : audit.verdict === "violated" ? "Scope validation failed" : audit.verdict === "partial" ? "Partial result — source availability warning" : "Recorded scope limits met"}</h2>
    {audit ? <>
      <dl className="grid gap-3 sm:grid-cols-2">
        <div><dt className="text-secondary">Saved report</dt><dd className="font-semibold">{audit.persisted.words} words{policy ? ` · ${wordBounds(policy)} requested` : " · requested bounds unavailable"}</dd></div>
        <div><dt className="text-secondary">Distinct consulted pages</dt><dd className="font-semibold">{audit.consulted_count}{policy?.max_sources != null ? ` · maximum ${policy.max_sources}` : " · requested cap unavailable"}</dd></div>
      </dl>
      <p className="text-muted">Counts include the complete saved report and all consulted pages, including snippets. Final citations do not replace the consulted count.</p>
      {audit.violations.length > 0 && <ul className="list-disc space-y-1 pl-5" aria-label="Scope violations">{audit.violations.map(value => <li key={value} className="break-words">{reason(value)}</li>)}</ul>}
      {audit.warnings.length > 0 && <ul className="list-disc space-y-1 pl-5" aria-label="Scope warnings">{audit.warnings.map(value => <li key={value} className="break-words">{reason(value)}</li>)}</ul>}
      {audit.unavailable.length > 0 && <ul className="space-y-2" aria-label="Unavailable sources">{audit.unavailable.map(({ url, reason: unavailableReason }) => <li key={url} className="break-all">{url}<span className="block text-secondary">{reason(unavailableReason)}</span></li>)}</ul>}
      <details><summary className="cursor-pointer rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">Count provenance</summary><p className="mt-2 break-all text-muted">{audit.counter_version} · {audit.controlling_surface}<br />SHA-256: {audit.persisted.sha256}</p></details>
    </> : <p className="text-secondary">This run has no readable persisted scope audit. Its status and legacy word or citation counts do not establish scope compliance.</p>}
    {(qualityWarning || quality.length > 0) && <div className="space-y-1 border-t border-line pt-3"><p className="font-semibold">Independent research quality warning{outcome.delivery_quality ? `: ${String(outcome.delivery_quality).replaceAll("_", " ")}` : ""}</p>{quality.length > 0 && <ul className="list-disc pl-5">{[...new Set(quality)].map(value => <li key={value} className="break-words">{reason(value)}</li>)}</ul>}</div>}
    <p className="text-secondary">Review and export any saved result below. A new research run requires an explicit reviewed submission.</p>
  </section>;
}
