import Link from "next/link";
import { useRouter } from "next/router";

import { AuthGate } from "@/components/AuthGate";
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
    return <p className="p-8 text-slate-200">Select a mission from the backlog to view details.</p>;
  }

  if (isLoading) {
    return <p className="p-8 text-slate-200">Loading mission…</p>;
  }

  if (error) {
    return (
      <div className="p-8 text-rose-300">
        Unable to load mission.
        <button onClick={refresh} className="ml-2 underline text-sky-300">
          Retry
        </button>
      </div>
    );
  }

  if (!mission) {
    return <p className="p-8 text-rose-300">Mission not found.</p>;
  }

  const handleCompleted = () => {
    refresh();
    refreshQuality();
  };

  return (
    <main className="px-6 py-10 md:px-10 space-y-8">
      <section className="glass-card p-6 flex flex-col gap-3">
        <div className="flex items-center gap-3 text-sm text-slate-300">
          <Link href="/missions" className="text-sky-300">
            ← Back to backlog
          </Link>
          <span>·</span>
          <span>Mission ID: {mission.mission_data.mission_id}</span>
        </div>
        <h1 className="text-4xl font-semibold text-white">{mission.mission_data.title ?? mission.mission_data.mission_id}</h1>
        <p className="text-slate-200 max-w-4xl">{mission.mission_data.summary}</p>
        <div className="flex flex-wrap gap-4 text-sm text-slate-300">
          <span>Status: {mission.mission_data.status}</span>
          <span>Owner: {mission.mission_data.owner ?? "Unassigned"}</span>
          <span>Completion: {mission.completion_percentage ?? 0}%</span>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[2fr,1fr]">
        <MissionProtocolForm mission={mission} onCompleted={handleCompleted} />
        <div className="space-y-6">
          <ProgressIndicator value={mission.completion_percentage ?? 0} />
          <QualityGatePanel mission={mission} report={report} />
          <div className="glass-card p-4 text-sm text-slate-300">
            <p>
              Real-time gate data fetched from <code>/api/v1/quality/missions/{mission.id}/quality</code>. Compare with heuristics in{" "}
              <code>docs/quality_gates.md</code>.
            </p>
          </div>
        </div>
      </section>
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
