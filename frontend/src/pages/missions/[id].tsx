import Link from "next/link";
import { useRouter } from "next/router";

import { AuthGate } from "@/components/AuthGate";
import { EvidenceCard } from "@/components/EvidenceCard";
import { MissionProtocolForm } from "@/components/MissionProtocolForm";
import { ProgressIndicator } from "@/components/ProgressIndicator";
import { QualityGatePanel } from "@/components/QualityGatePanel";
import { useMissionDetail, useQualityReport } from "@/lib/hooks/useMissions";

function MissionDetailContent() {
  const router = useRouter();
  const missionId = typeof router.query.id === "string" ? router.query.id : undefined;

  const { mission, isLoading, error, refresh } = useMissionDetail(missionId);
  const { report, refresh: refreshQuality } = useQualityReport(missionId);

  if (!missionId) {
    return <p className="p-8 text-slate-600">Select a mission from the backlog to view details.</p>;
  }

  if (isLoading) {
    return <p className="p-8 text-slate-600">Loading mission…</p>;
  }

  if (error) {
    return (
      <div className="rounded-3xl border border-rose-200 bg-rose-50 p-8 text-rose-700">
        Unable to load mission.
        <button onClick={refresh} className="ml-2 font-semibold text-rose-900 underline">
          Retry
        </button>
      </div>
    );
  }

  if (!mission) {
    return <p className="p-8 text-rose-700">Mission not found.</p>;
  }

  const handleCompleted = () => {
    refresh();
    refreshQuality();
  };

  return (
    <main className="min-h-screen bg-slate-50 py-10">
      <div className="mx-auto flex max-w-7xl flex-col gap-8 px-4 text-slate-900 sm:px-6 lg:px-8">
        <section className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
          <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500">
            <Link href="/missions" className="font-medium text-sky-700">
              ← Back to backlog
            </Link>
            <span>·</span>
            <span>Mission ID: {mission.mission_data.mission_id}</span>
          </div>
          <h1 className="mt-3 text-4xl font-semibold text-slate-900">{mission.mission_data.title ?? mission.mission_data.mission_id}</h1>
          <p className="mt-3 max-w-4xl text-base leading-relaxed text-slate-600">{mission.mission_data.summary}</p>
          <div className="mt-4 flex flex-wrap gap-4 text-sm text-slate-600">
            <span>Status: {mission.mission_data.status}</span>
            <span>Owner: {mission.mission_data.owner ?? "Unassigned"}</span>
            <span>Completion: {mission.completion_percentage ?? 0}%</span>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[2fr,1fr]">
          <MissionProtocolForm mission={mission} onCompleted={handleCompleted} />
          <div className="space-y-6">
            <ProgressIndicator value={mission.completion_percentage ?? 0} mission={mission} />
            <QualityGatePanel mission={mission} report={report} />
            <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              <p>
                Real-time gate data fetched from <code>/api/v1/quality/missions/{mission.id}/quality</code>. Compare with heuristics in{" "}
                <code>docs/quality_gates.md</code> to see why a gate is blocking.
              </p>
            </div>
          </div>
        </section>

        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">Evidence</p>
              <h2 className="text-2xl font-semibold text-slate-900">Linked sources</h2>
            </div>
            <span className="text-sm font-medium text-slate-500">{mission.mission_data.evidence.length} record(s)</span>
          </div>
          {mission.mission_data.evidence.length === 0 ? (
            <p className="mt-4 text-sm text-slate-600">
              No evidence linked yet. Use the search workspace → quick add action to capture supporting chunks.
            </p>
          ) : (
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              {mission.mission_data.evidence.map((item, index) => (
                <EvidenceCard key={item.evidence_id || index} evidence={item} index={index} />
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

export default function MissionDetailPage() {
  return (
    <AuthGate>
      <MissionDetailContent />
    </AuthGate>
  );
}
