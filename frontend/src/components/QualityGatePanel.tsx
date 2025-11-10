import { formatDistanceToNow } from "date-fns";

import type { Mission, QualityGateName, QualityGateReport } from "@/types/mission";

const GATE_DESCRIPTIONS: Record<string, string> = {
  research_statement: "Topic, scope, objective, methodology, and success metrics anchor the mission.",
  evidence_links: "Each key insight has at least one linked chunk supporting the claim.",
  contradictions_resolved: "Conflicting findings include a resolution statement.",
  synthesis_quality: "Synthesis contains insights, recommendations, and next steps with Markdown support.",
  traceability: "Evidence tracks chunk + insight IDs for audit trails.",
};

const STATUS_TOKENS: Record<string, { label: string; className: string; icon: string }> = {
  pass: { label: "Pass", className: "border-emerald-200 bg-emerald-50 text-emerald-700", icon: "✓" },
  fail: { label: "Fail", className: "border-rose-200 bg-rose-50 text-rose-700", icon: "!" },
  pending: { label: "Pending", className: "border-amber-200 bg-amber-50 text-amber-700", icon: "…" },
};

const RECOMMENDATIONS: Record<string, string> = {
  research_statement: "Fill in topic, objective, scope, and at least one success metric.",
  evidence_links: "Attach summaries + chunk IDs for every key insight.",
  contradictions_resolved: "Call out the contradiction and describe how you resolved it.",
  synthesis_quality: "Add Markdown insights plus next steps to clear this gate.",
  traceability: "Use Quick Add from search to capture chunk + mission linkage automatically.",
};

type GateSnapshot = QualityGateReport["gates"][QualityGateName];

type Props = {
  report?: QualityGateReport;
  mission?: Mission;
};

export function QualityGatePanel({ report, mission }: Props) {
  const fallback = mission?.mission_data.quality_checkpoints?.reduce<Partial<Record<QualityGateName, GateSnapshot>>>(
    (acc, checkpoint) => {
      acc[checkpoint.gate] = {
        gate: checkpoint.gate,
        status: checkpoint.status,
        blocking: true,
        details: checkpoint.notes ?? undefined,
        evaluated_at: checkpoint.validated_at ?? mission?.updated_at ?? new Date().toISOString(),
        metadata: null,
      };
      return acc;
    },
    {},
  );

  const checkpoints: Partial<Record<QualityGateName, GateSnapshot>> = report?.gates ?? fallback ?? {};

  const gates = (Object.keys(GATE_DESCRIPTIONS) as QualityGateName[]).map((gate) => {
    const snapshot = checkpoints[gate];
    return {
      name: gate,
      status: snapshot?.status ?? "pending",
      details: snapshot?.details,
      evaluatedAt: snapshot?.evaluated_at,
      metadata: snapshot?.metadata,
    };
  });

  const failing = gates.filter((gate) => gate.status === "fail").length;

  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-6 text-slate-900 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">Quality gates</p>
          <h3 className="text-2xl font-semibold text-slate-900">Research readiness</h3>
        </div>
        <div className={`text-sm font-medium ${failing === 0 ? "text-emerald-700" : "text-rose-700"}`}>
          {failing === 0 ? "All gates passing" : `${failing} blocking gate(s)`}
        </div>
      </div>
      <p className="mt-2 text-sm text-slate-600">
        Evaluations mirror docs/quality_gates.md. Refresh mission data after editing fields to re-run automation.
      </p>
      <div className="mt-4 space-y-3">
        {gates.map((gate) => {
          const token = STATUS_TOKENS[gate.status] ?? STATUS_TOKENS.pending;
          return (
            <div
              key={gate.name}
              data-testid={`gate-${gate.name}`}
              className="rounded-2xl border border-slate-200 bg-slate-50 p-4"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-lg font-semibold capitalize">{gate.name.replace("_", " ")}</p>
                  <p className="text-sm text-slate-600">{GATE_DESCRIPTIONS[gate.name]}</p>
                </div>
                <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${token.className}`}>
                  <span>{token.icon}</span>
                  {token.label}
                </span>
              </div>
              <div className="mt-3 text-sm text-slate-600">
                <p>{RECOMMENDATIONS[gate.name]}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {gate.evaluatedAt ? `Evaluated ${formatDistanceToNow(new Date(gate.evaluatedAt))} ago` : "Awaiting evaluation"}
                  {gate.details && <span className="ml-1 text-rose-600">· {gate.details}</span>}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
