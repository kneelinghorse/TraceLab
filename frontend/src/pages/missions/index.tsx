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
  const { failing, passing } = gateSummary(formMission);

  return (
    <main className="min-h-screen bg-slate-50 py-10">
      <div className="mx-auto flex max-w-7xl flex-col gap-8 px-4 text-slate-900 sm:px-6 lg:px-8">
        <section className="grid gap-6 rounded-3xl border border-slate-200 bg-white p-8 shadow-sm lg:grid-cols-[2fr,1fr]">
          <div className="space-y-4">
            <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-500">Mission Protocol</p>
            <h1 className="text-4xl font-semibold text-slate-900">UI Integration + Quality Gates</h1>
            <p className="text-base text-slate-600">
              Capture structured research directly inside TraceLab, promote semantic-search evidence, and watch gate status update in
              real time. Layout favors readability with generous spacing and clear hierarchy.
            </p>
            <div className="flex flex-wrap gap-3">
              <button
                className={`rounded-full border px-5 py-2 text-sm font-semibold transition ${
                  mode === "create"
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-300 bg-white text-slate-900 hover:border-slate-500"
                }`}
                onClick={() => setMode("create")}
              >
                Start New Mission
              </button>
              <button
                className={`rounded-full border px-5 py-2 text-sm font-semibold transition ${
                  mode === "edit"
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-300 bg-white text-slate-900 hover:border-slate-500"
                }`}
                onClick={() => setMode("edit")}
                disabled={!activeMission}
              >
                Edit selected mission
              </button>
            </div>
            {formMission && (
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                <p className="font-medium text-slate-900">{formMission.mission_data.title ?? formMission.mission_data.mission_id}</p>
                <p>
                  {formMission.completion_percentage ?? 0}% complete · {failing} failing gate(s) · {passing} passing gate(s)
                </p>
              </div>
            )}
          </div>
          <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-5 text-sm text-slate-600">
            <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-500">Quality reference</p>
            <p className="mt-3 leading-relaxed">
              Widgets map to Pydantic validators shipped in Sprint 03. Keep docs/quality_gates.md handy—every field in the form is
              annotated so you know which gate it unlocks.
            </p>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[2fr,1fr]">
          <MissionProtocolForm mission={formMission} onCompleted={handleFormCompleted} />
          <div className="space-y-6">
            <ProgressIndicator value={formMission?.completion_percentage ?? 0} mission={formMission} />
            <QualityGatePanel mission={formMission} />
          </div>
        </section>

        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-500">Missions</p>
              <h2 className="text-2xl font-semibold text-slate-900">Mission Protocol Backlog</h2>
            </div>
            <button onClick={refresh} className="text-sm font-medium text-slate-600 hover:text-slate-900">
              Refresh
            </button>
          </div>
          {error && <p className="mt-3 text-sm text-rose-600">Unable to load missions: {error.message}</p>}
          {isLoading ? (
            <p className="mt-3 text-sm text-slate-600">Loading missions…</p>
          ) : (
            <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {missions.map((mission) => {
                const isActive = mission.id === highlightedMissionId;
                const failingGates = mission.mission_data.quality_checkpoints.filter((gate) => gate.status === "fail").length;
                const completion = mission.completion_percentage ?? 0;
                return (
                  <button
                    key={mission.id}
                    onClick={() => handleSelectMission(mission)}
                    className={`text-left rounded-2xl border p-5 transition ${
                      isActive
                        ? "border-slate-900 bg-slate-900 text-white shadow-lg shadow-slate-900/15"
                        : "border-slate-200 bg-white text-slate-900 hover:border-slate-400"
                    }`}
                  >
                    <p className={`text-xs font-semibold uppercase tracking-[0.3em] ${isActive ? "text-white/70" : "text-slate-500"}`}>
                      {mission.mission_data.status}
                    </p>
                    <h3 className={`mt-1 text-xl font-semibold ${isActive ? "text-white" : "text-slate-900"}`}>
                      {mission.mission_data.title ?? mission.mission_data.mission_id}
                    </h3>
                    <p className={`text-sm ${isActive ? "text-white/80" : "text-slate-600"}`}>
                      {mission.mission_data.summary ?? "Summary pending"}
                    </p>
                    <div className={`mt-4 flex items-center justify-between text-sm ${isActive ? "text-white/80" : "text-slate-600"}`}>
                      <span>{completion}% complete</span>
                      <span className={failingGates ? "text-rose-500" : "text-emerald-600"}>
                        {failingGates ? `${failingGates} failing gate(s)` : "All gates passing"}
                      </span>
                    </div>
                    <Link
                      href={`/missions/${mission.id}`}
                      className={`mt-3 inline-flex items-center gap-1 text-sm font-semibold ${isActive ? "text-white" : "text-sky-700"}`}
                      onClick={(event) => event.stopPropagation()}
                    >
                      View details →
                    </Link>
                  </button>
                );
              })}
              {missions.length === 0 && (
                <p className="text-sm text-slate-600">No missions found. Create one to get started.</p>
              )}
            </div>
          )}
        </section>
      </div>
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
