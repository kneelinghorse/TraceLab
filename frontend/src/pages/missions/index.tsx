import { useMemo, useState } from "react";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { MissionProtocolForm } from "@/components/MissionProtocolForm";
import { ProgressIndicator } from "@/components/ProgressIndicator";
import { QualityGatePanel } from "@/components/QualityGatePanel";
import { useMissionList } from "@/lib/hooks/useMissions";
import type { Mission } from "@/types/mission";

type FormMode = "create" | "edit";

const gateSummary = (mission?: Mission) => {
  const gates = mission?.mission_data.quality_checkpoints ?? [];
  const failing = gates.filter((gate) => gate.status === "fail").length;
  const passing = gates.filter((gate) => gate.status === "pass").length;
  return { failing, passing };
};

function MissionsContent() {
  const { missions, isLoading, error, refresh } = useMissionList();
  const [mode, setMode] = useState<FormMode>("edit");
  const [selectedMissionId, setSelectedMissionId] = useState<string | undefined>(undefined);

  const activeMission = useMemo(() => {
    if (!missions.length) {
      return undefined;
    }
    if (!selectedMissionId) {
      return missions[0];
    }
    return missions.find((mission) => mission.id === selectedMissionId) ?? missions[0];
  }, [missions, selectedMissionId]);

  const handleSelectMission = (mission: Mission) => {
    setSelectedMissionId(mission.id);
    setMode("edit");
  };

  const handleFormCompleted = (mission: Mission) => {
    setSelectedMissionId(mission.id);
    setMode("edit");
    refresh();
  };

  const formMission = mode === "edit" ? activeMission : undefined;
  const highlightedMissionId = selectedMissionId ?? activeMission?.id;
  const { failing } = gateSummary(formMission);

  return (
    <main className="px-6 py-10 md:px-10 space-y-8">
      <section className="glass-card p-6 grid gap-6 lg:grid-cols-[2fr,1fr]">
        <div className="space-y-4">
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Mission Protocol</p>
          <h1 className="text-4xl font-semibold text-white">UI Integration + Quality Gates</h1>
          <p className="text-slate-200 text-lg">
            Sprint 03 focuses on surfacing the Mission Protocol data model inside a research-friendly UI. Components map directly
            to the validation & gate logic defined in <code>docs/quality_gates.md</code>.
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              className={`px-4 py-2 rounded-full text-sm font-semibold border ${mode === "create" ? "bg-white text-slate-900" : "text-white border-white/30"}`}
              onClick={() => setMode("create")}
            >
              Start New Mission
            </button>
            <button
              className={`px-4 py-2 rounded-full text-sm font-semibold border ${mode === "edit" ? "bg-white text-slate-900" : "text-white border-white/30"}`}
              onClick={() => setMode("edit")}
              disabled={!activeMission}
            >
              Edit Selected Mission
            </button>
          </div>
          {formMission && (
            <p className="text-sm text-slate-300">
              Editing <strong>{formMission.mission_data.title ?? formMission.mission_data.mission_id}</strong> ·{" "}
              {formMission.completion_percentage ?? 0}% complete · {failing} failing gate(s)
            </p>
          )}
        </div>
        <div className="glass-card p-4 bg-slate-900/40 border border-white/5 rounded-2xl">
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Quality Reference</p>
          <p className="text-sm text-slate-200 mt-3">
            Each UI widget lines up with the backend Pydantic validators shipped in B3.1-B3.3. Blocking gates enforce the research
            rigor heuristics described in <code>docs/quality_gates.md</code>.
          </p>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[2fr,1fr]">
        <MissionProtocolForm mission={formMission} onCompleted={handleFormCompleted} />
        <div className="space-y-6">
          <ProgressIndicator value={formMission?.completion_percentage ?? 0} />
          <QualityGatePanel mission={formMission} />
        </div>
      </section>

      <section className="glass-card p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Missions</p>
            <h2 className="text-2xl font-semibold text-white">Mission Protocol Backlog</h2>
          </div>
          <button onClick={refresh} className="text-sm text-slate-300 hover:text-white">
            Refresh
          </button>
        </div>
        {error && <p className="text-rose-300 text-sm">Unable to load missions: {error.message}</p>}
        {isLoading ? (
          <p className="text-slate-300 text-sm">Loading missions…</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {missions.map((mission) => {
              const isActive = mission.id === highlightedMissionId;
              const failingGates = mission.mission_data.quality_checkpoints.filter((gate) => gate.status === "fail").length;
              return (
                <button
                  key={mission.id}
                  onClick={() => handleSelectMission(mission)}
                  className={`text-left rounded-2xl border p-4 transition hover:border-sky-300/60 ${
                    isActive ? "border-sky-400/70 bg-sky-400/5" : "border-white/10 bg-white/5"
                  }`}
                >
                  <p className="text-xs uppercase tracking-[0.3em] text-slate-400">{mission.mission_data.status}</p>
                  <h3 className="text-xl font-semibold text-white mt-1">{mission.mission_data.title ?? mission.mission_data.mission_id}</h3>
                  <p className="text-sm text-slate-300 overflow-hidden text-ellipsis">
                    {mission.mission_data.summary ?? "Summary pending"}
                  </p>
                  <div className="flex items-center justify-between text-sm text-slate-300 mt-4">
                    <span>{mission.completion_percentage ?? 0}% complete</span>
                    <span className={failingGates ? "text-rose-300" : "text-emerald-300"}>
                      {failingGates ? `${failingGates} failing gates` : "All gates passing"}
                    </span>
                  </div>
                  <Link
                    href={`/missions/${mission.id}`}
                    className="text-sm text-sky-300 inline-flex items-center gap-1 mt-3"
                    onClick={(event) => event.stopPropagation()}
                  >
                    View details →
                  </Link>
                </button>
              );
            })}
            {missions.length === 0 && <p className="text-sm text-slate-300">No missions found. Create one to get started.</p>}
          </div>
        )}
      </section>
    </main>
  );
}

export default function MissionsPage() {
  return (
    <AuthGate>
      <MissionsContent />
    </AuthGate>
  );
}
