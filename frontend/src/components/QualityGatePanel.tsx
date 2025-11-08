import { formatDistanceToNow } from "date-fns";

import type { Mission, QualityGateName, QualityGateReport } from "@/types/mission";

const GATE_DESCRIPTIONS: Record<string, string> = {
  research_statement: "Topic, scope, and objective must be populated.",
  evidence_links: "Each insight references at least one supporting chunk.",
  contradictions_resolved: "Contradictions include an explicit resolution.",
  synthesis_quality: "Synthesis includes ≥40 chars, recommendations, and next steps.",
  traceability: "Evidence maintains chunk + insight references for auditability.",
};

const STATUS_COLORS: Record<string, string> = {
  pass: "text-emerald-400 bg-emerald-400/10 border-emerald-400/40",
  fail: "text-rose-300 bg-rose-400/10 border-rose-400/40",
  pending: "text-yellow-300 bg-yellow-300/10 border-yellow-300/40",
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
    <div className="glass-card p-6 space-y-4">
      <div>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.25em] text-slate-400">Quality Gates</p>
            <h3 className="text-2xl font-semibold text-white mt-1">Research Readiness</h3>
          </div>
          <div className="text-sm text-slate-300">
            {failing === 0 ? (
              <span className="text-emerald-300">All gates passing</span>
            ) : (
              <span className="text-rose-300">{failing} blocking gate(s)</span>
            )}
          </div>
        </div>
        <p className="text-sm text-slate-400 mt-2">
          Gates mirror the heuristics documented in <code>docs/quality_gates.md</code>. UI polls{" "}
          <code>/api/v1/quality/missions/:id/quality</code> every 15s for fresh evaluations.
        </p>
      </div>
      <div className="grid gap-3">
        {gates.map((gate) => (
          <div
            key={gate.name}
            data-testid={`gate-${gate.name}`}
            className="border border-white/5 rounded-xl p-4 bg-white/5 bg-opacity-10 backdrop-blur"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="text-lg font-semibold capitalize">{gate.name.replace("_", " ")}</p>
                <p className="text-sm text-slate-300">{GATE_DESCRIPTIONS[gate.name]}</p>
              </div>
              <span
                className={`px-3 py-1 text-xs font-semibold rounded-full border ${STATUS_COLORS[gate.status] ?? STATUS_COLORS.pending}`}
              >
                {gate.status}
              </span>
            </div>
            <div className="mt-3 text-sm text-slate-300 flex items-center gap-2">
              <span className="opacity-70">
                {gate.evaluatedAt ? `Evaluated ${formatDistanceToNow(new Date(gate.evaluatedAt))} ago` : "Awaiting evaluation"}
              </span>
              {gate.details && <span className="text-rose-200">· {gate.details}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
