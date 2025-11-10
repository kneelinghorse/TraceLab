import clsx from "clsx";
import Link from "next/link";
import { forwardRef, useState } from "react";

import type { Document } from "@/types/document";
import type { Mission } from "@/types/mission";
import type { SearchResultChunk } from "@/types/search";

type ResultCardProps = {
  result: SearchResultChunk;
  document?: Document;
  missions: Mission[];
  onQuickAddEvidence: (missionId: string, result: SearchResultChunk) => Promise<void>;
  isHighlighted?: boolean;
};

type Feedback = {
  type: "success" | "error";
  message: string;
} | null;

export const ResultCard = forwardRef<HTMLDivElement, ResultCardProps>(function ResultCard(
  { result, document, missions, onQuickAddEvidence, isHighlighted = false },
  ref,
) {
  const [selectedMission, setSelectedMission] = useState<string>("");
  const [isLinking, setIsLinking] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);

  const documentLabel = document?.name ?? document?.file_path ?? result.document_id ?? "Unlinked document";
  const chunkPreview = result.content.length > 360 ? `${result.content.slice(0, 357)}…` : result.content;
  const scoreLabel = typeof result.score === "number" ? result.score.toFixed(3) : "–";

  const handleQuickAdd = async () => {
    if (!selectedMission) {
      setFeedback({ type: "error", message: "Select a mission before adding evidence." });
      return;
    }

    setFeedback(null);
    setIsLinking(true);
    try {
      await onQuickAddEvidence(selectedMission, result);
      const mission = missions.find((item) => item.id === selectedMission);
      setFeedback({
        type: "success",
        message: mission
          ? `Linked to ${mission.mission_data.title ?? mission.mission_data.mission_id}`
          : "Evidence added",
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to add evidence";
      setFeedback({ type: "error", message });
    } finally {
      setIsLinking(false);
    }
  };

  return (
    <div
      ref={ref}
      className={clsx(
        "rounded-2xl border p-5 transition bg-white/5 backdrop-blur text-white/90",
        isHighlighted
          ? "border-amber-300 shadow-lg shadow-amber-500/30"
          : "border-white/10 hover:border-sky-300/60",
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Chunk score</p>
          <p className="text-2xl font-semibold text-sky-200">{scoreLabel}</p>
        </div>
        {result.chunk_id && (
          <code className="rounded-full border border-white/15 bg-black/30 px-3 py-1 text-xs text-slate-200">
            {result.chunk_id}
          </code>
        )}
      </div>

      <div className="mt-4 space-y-2">
        <p className="text-sm text-slate-300">{documentLabel}</p>
        <p className="text-sm text-slate-400">
          {result.source_type ? result.source_type : "Unknown type"}
          {document?.uploaded_at && (
            <span className="ml-2 text-xs text-slate-500">
              Uploaded {new Date(document.uploaded_at).toLocaleDateString()}
            </span>
          )}
        </p>
      </div>

      <p className="mt-4 text-slate-100 leading-relaxed whitespace-pre-line">{chunkPreview}</p>

      <div className="mt-4 flex flex-wrap items-center gap-4 text-sm text-sky-300">
        {document?.id && (
          <Link href={`/documents/${document.id}`} className="hover:underline">
            View document ↗
          </Link>
        )}
        {result.project_id && <span className="text-slate-400">Project: {result.project_id}</span>}
      </div>

      <div className="mt-5 space-y-2 rounded-2xl border border-white/10 bg-slate-900/30 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={selectedMission}
            onChange={(event) => setSelectedMission(event.target.value)}
            className="flex-1 rounded-xl border border-white/15 bg-black/20 px-3 py-2 text-sm text-white focus:outline-none"
          >
            <option value="">Select mission…</option>
            {missions.map((mission) => (
              <option key={mission.id} value={mission.id} className="bg-slate-900 text-white">
                {mission.mission_data.title ?? mission.mission_data.mission_id}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={!selectedMission || isLinking}
            onClick={handleQuickAdd}
            className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-white shadow shadow-emerald-500/30 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isLinking ? "Linking…" : "Quick add"}
          </button>
        </div>
        {feedback && (
          <p className={clsx("text-sm", feedback.type === "success" ? "text-emerald-300" : "text-rose-300")}>{feedback.message}</p>
        )}
      </div>
    </div>
  );
});
