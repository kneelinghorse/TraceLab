import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { formatDistanceToNow } from "date-fns";

import { AuthGate } from "@/components/AuthGate";
import { ExecutionTimeline, ResearchPhases, ResultLinks } from "@/components/missions";
import { missionsApi } from "@/lib/api/missions";
import { useApiMission } from "@/lib/hooks/useMissions";
import type { MissionStatus, ReportPromotionResponse, ApiMissionUpdate } from "@/types/mission";

const STATUS_COLORS: Record<MissionStatus, { bg: string; text: string; dot: string }> = {
  draft: { bg: "bg-gray-100 dark:bg-gray-700", text: "text-gray-700 dark:text-gray-300", dot: "bg-gray-400" },
  queued: { bg: "bg-amber-100 dark:bg-amber-900/30", text: "text-amber-700 dark:text-amber-300", dot: "bg-amber-400" },
  in_progress: { bg: "bg-blue-100 dark:bg-blue-900/30", text: "text-blue-700 dark:text-blue-300", dot: "bg-blue-400" },
  completed: { bg: "bg-emerald-100 dark:bg-emerald-900/30", text: "text-emerald-700 dark:text-emerald-300", dot: "bg-emerald-400" },
  blocked: { bg: "bg-red-100 dark:bg-red-900/30", text: "text-red-700 dark:text-red-300", dot: "bg-red-400" },
  cancelled: { bg: "bg-gray-100 dark:bg-gray-700", text: "text-gray-500 dark:text-gray-400", dot: "bg-gray-300" },
};

function StatusBadge({ status }: { status: MissionStatus }) {
  const colors = STATUS_COLORS[status] ?? STATUS_COLORS.draft;
  const label = status.replace("_", " ");

  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium ${colors.bg} ${colors.text}`}>
      <span className={`w-2 h-2 rounded-full ${colors.dot}`} />
      {label.charAt(0).toUpperCase() + label.slice(1)}
    </span>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="p-6 border-b border-gray-200 dark:border-gray-700 last:border-b-0">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{title}</h2>
      {children}
    </div>
  );
}

function MissionDetailContent() {
  const router = useRouter();
  const missionId = typeof router.query.id === "string" ? router.query.id : undefined;
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isPromoting, setIsPromoting] = useState(false);
  const [promotionResult, setPromotionResult] = useState<ReportPromotionResponse | null>(null);
  const [promotionError, setPromotionError] = useState<string | null>(null);

  // Edit mode state
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editObjective, setEditObjective] = useState("");
  const [editSuccessCriteria, setEditSuccessCriteria] = useState<string[]>([]);
  const [editDeliverables, setEditDeliverables] = useState<string[]>([]);
  const [editTags, setEditTags] = useState<string[]>([]);
  const [editError, setEditError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const { mission, isLoading, error, refresh } = useApiMission(missionId);

  const handleSubmitToDeepSearch = async () => {
    if (!missionId) return;

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await missionsApi.submitToDeepSearch(missionId);
      refresh();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to submit mission");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!missionId) return;
    if (!confirm("Are you sure you want to delete this mission?")) return;

    try {
      await missionsApi.delete(missionId);
      router.push("/missions");
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete mission");
    }
  };

  const handlePromoteReport = async () => {
    if (!missionId) return;

    setIsPromoting(true);
    setPromotionError(null);
    setPromotionResult(null);

    try {
      const result = await missionsApi.promoteReport(missionId);
      setPromotionResult(result);
      refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to promote report";
      // Check for already promoted error (409)
      if (message.includes("already been promoted")) {
        setPromotionError("Report has already been promoted to a document.");
      } else {
        setPromotionError(message);
      }
    } finally {
      setIsPromoting(false);
    }
  };

  // Edit mode handlers
  const handleStartEdit = () => {
    if (!mission) return;
    setEditTitle(mission.title);
    setEditObjective(mission.objective);
    setEditSuccessCriteria([...mission.success_criteria]);
    setEditDeliverables([...mission.deliverables]);
    setEditTags([...mission.tags]);
    setEditError(null);
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditError(null);
  };

  const handleSaveEdit = async () => {
    if (!missionId || !mission) return;

    if (!editTitle.trim()) {
      setEditError("Title is required");
      return;
    }
    if (!editObjective.trim()) {
      setEditError("Objective is required");
      return;
    }

    setEditError(null);
    setIsSaving(true);

    try {
      const updateData: ApiMissionUpdate = {
        title: editTitle.trim(),
        objective: editObjective.trim(),
        success_criteria: editSuccessCriteria.filter(c => c.trim() !== ""),
        deliverables: editDeliverables.filter(d => d.trim() !== ""),
        tags: editTags.filter(t => t.trim() !== ""),
      };

      await missionsApi.update(missionId, updateData);
      setIsEditing(false);
      refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update mission";
      setEditError(message);
    } finally {
      setIsSaving(false);
    }
  };

  // List editing helpers
  const handleAddListItem = (
    setter: React.Dispatch<React.SetStateAction<string[]>>
  ) => {
    setter(prev => [...prev, ""]);
  };

  const handleUpdateListItem = (
    setter: React.Dispatch<React.SetStateAction<string[]>>,
    index: number,
    value: string
  ) => {
    setter(prev => {
      const updated = [...prev];
      updated[index] = value;
      return updated;
    });
  };

  const handleRemoveListItem = (
    setter: React.Dispatch<React.SetStateAction<string[]>>,
    index: number
  ) => {
    setter(prev => prev.filter((_, i) => i !== index));
  };

  if (!missionId) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
        <div className="max-w-4xl mx-auto px-4">
          <p className="text-gray-600 dark:text-gray-400">Select a mission to view details.</p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
        <div className="max-w-4xl mx-auto px-4">
          <p className="text-gray-600 dark:text-gray-400">Loading mission...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
        <div className="max-w-4xl mx-auto px-4">
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
            <p className="text-red-600 dark:text-red-400">
              Failed to load mission: {error.message}
            </p>
            <button
              onClick={refresh}
              className="mt-2 text-sm font-medium text-red-700 dark:text-red-300 underline"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!mission) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
        <div className="max-w-4xl mx-auto px-4">
          <p className="text-gray-600 dark:text-gray-400">Mission not found.</p>
        </div>
      </div>
    );
  }

  const createdAt = mission.created_at
    ? formatDistanceToNow(new Date(mission.created_at), { addSuffix: true })
    : null;
  const isDraft = mission.status === "draft";
  const hasResearchPhases = Object.keys(mission.research_phases).length > 0;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-6 flex items-center justify-between">
          <Link
            href="/missions"
            className="inline-flex items-center text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700"
          >
            &larr; Back to missions
          </Link>
          <div className="flex items-center gap-2">
            <button
              onClick={refresh}
              className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white border border-gray-300 dark:border-gray-600 rounded-lg"
            >
              Refresh
            </button>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
          {/* Header Section */}
          <div className="p-6 border-b border-gray-200 dark:border-gray-700">
            {isEditing ? (
              /* Edit Mode Form */
              <div className="space-y-6">
                <div className="flex items-center gap-3 mb-4">
                  <StatusBadge status={mission.status} />
                  <span className="text-sm font-mono text-gray-500 dark:text-gray-400">
                    {mission.mission_id}
                  </span>
                  <span className="px-2 py-1 text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded">
                    Editing
                  </span>
                </div>

                {/* Title */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Title *
                  </label>
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    autoFocus
                  />
                </div>

                {/* Objective */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Objective *
                  </label>
                  <textarea
                    value={editObjective}
                    onChange={(e) => setEditObjective(e.target.value)}
                    rows={3}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>

                {/* Success Criteria */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Success Criteria
                  </label>
                  <div className="space-y-2">
                    {editSuccessCriteria.map((criterion, index) => (
                      <div key={index} className="flex gap-2">
                        <input
                          type="text"
                          value={criterion}
                          onChange={(e) => handleUpdateListItem(setEditSuccessCriteria, index, e.target.value)}
                          className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                          placeholder="Enter success criterion"
                        />
                        <button
                          type="button"
                          onClick={() => handleRemoveListItem(setEditSuccessCriteria, index)}
                          className="px-3 py-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg"
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() => handleAddListItem(setEditSuccessCriteria)}
                      className="px-3 py-2 text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg"
                    >
                      + Add Criterion
                    </button>
                  </div>
                </div>

                {/* Deliverables */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Deliverables
                  </label>
                  <div className="space-y-2">
                    {editDeliverables.map((deliverable, index) => (
                      <div key={index} className="flex gap-2">
                        <input
                          type="text"
                          value={deliverable}
                          onChange={(e) => handleUpdateListItem(setEditDeliverables, index, e.target.value)}
                          className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                          placeholder="Enter deliverable"
                        />
                        <button
                          type="button"
                          onClick={() => handleRemoveListItem(setEditDeliverables, index)}
                          className="px-3 py-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg"
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() => handleAddListItem(setEditDeliverables)}
                      className="px-3 py-2 text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg"
                    >
                      + Add Deliverable
                    </button>
                  </div>
                </div>

                {/* Tags */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Tags
                  </label>
                  <div className="space-y-2">
                    {editTags.map((tag, index) => (
                      <div key={index} className="flex gap-2">
                        <input
                          type="text"
                          value={tag}
                          onChange={(e) => handleUpdateListItem(setEditTags, index, e.target.value)}
                          className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                          placeholder="Enter tag"
                        />
                        <button
                          type="button"
                          onClick={() => handleRemoveListItem(setEditTags, index)}
                          className="px-3 py-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg"
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() => handleAddListItem(setEditTags)}
                      className="px-3 py-2 text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg"
                    >
                      + Add Tag
                    </button>
                  </div>
                </div>

                {/* Error Display */}
                {editError && (
                  <p className="text-sm text-red-600 dark:text-red-400">{editError}</p>
                )}

                {/* Save/Cancel Buttons */}
                <div className="flex gap-3 pt-2">
                  <button
                    onClick={handleSaveEdit}
                    disabled={isSaving}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
                  >
                    {isSaving ? "Saving..." : "Save Changes"}
                  </button>
                  <button
                    onClick={handleCancelEdit}
                    disabled={isSaving}
                    className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              /* View Mode */
              <>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-2">
                      <StatusBadge status={mission.status} />
                      <span className="text-sm font-mono text-gray-500 dark:text-gray-400">
                        {mission.mission_id}
                      </span>
                    </div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                      {mission.title}
                    </h1>
                    {createdAt && (
                      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        Created {createdAt}
                      </p>
                    )}
                  </div>
                </div>

                {mission.tags.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {mission.tags.map((tag) => (
                      <span
                        key={tag}
                        className="px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                {/* Action Buttons */}
                <div className="mt-6 flex flex-wrap gap-3">
                  {isDraft && (
                    <button
                      onClick={handleSubmitToDeepSearch}
                      disabled={isSubmitting}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium text-sm"
                    >
                      {isSubmitting ? "Submitting..." : "Submit to DeepSearch"}
                    </button>
                  )}
                  {mission.status === "completed" && (mission.result_report_id || mission.result_markdown) && !promotionResult && mission.result_document_ids.length === 0 && (
                    <button
                      onClick={handlePromoteReport}
                      disabled={isPromoting}
                      className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium text-sm"
                    >
                      {isPromoting ? "Promoting..." : "Promote to Document"}
                    </button>
                  )}
                  {promotionResult && (
                    <Link
                      href={`/documents/${promotionResult.document_id}`}
                      className="px-4 py-2 bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 rounded-lg hover:bg-emerald-200 dark:hover:bg-emerald-900/50 transition-colors font-medium text-sm"
                    >
                      View Promoted Document
                    </Link>
                  )}
                  {!promotionResult && mission.result_document_ids.length > 0 && (
                    <Link
                      href={`/documents/${mission.result_document_ids[0]}`}
                      className="px-4 py-2 bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 rounded-lg hover:bg-emerald-200 dark:hover:bg-emerald-900/50 transition-colors font-medium text-sm"
                    >
                      View Promoted Document
                    </Link>
                  )}
                  <button
                    onClick={handleStartEdit}
                    className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors font-medium text-sm"
                  >
                    Edit Mission
                  </button>
                  <button
                    onClick={handleDelete}
                    className="px-4 py-2 border border-red-300 dark:border-red-800 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors font-medium text-sm"
                  >
                    Delete
                  </button>
                </div>
              </>
            )}

            {submitError && (
              <p className="mt-3 text-sm text-red-600 dark:text-red-400">{submitError}</p>
            )}
            {promotionError && (
              <p className="mt-3 text-sm text-red-600 dark:text-red-400">{promotionError}</p>
            )}
            {promotionResult && (
              <p className="mt-3 text-sm text-emerald-600 dark:text-emerald-400">
                {promotionResult.message}
                {promotionResult.chunk_count !== null && ` (${promotionResult.chunk_count} chunks created)`}
              </p>
            )}
          </div>

          {/* Objective Section */}
          <Section title="Objective">
            <p className="text-gray-600 dark:text-gray-300 whitespace-pre-wrap">
              {mission.objective}
            </p>
          </Section>

          {/* Success Criteria Section */}
          {mission.success_criteria.length > 0 && (
            <Section title="Success Criteria">
              <ul className="space-y-2">
                {mission.success_criteria.map((criterion, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-gray-400 flex-shrink-0" />
                    <span className="text-gray-600 dark:text-gray-300">{criterion}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {/* Deliverables Section */}
          {mission.deliverables.length > 0 && (
            <Section title="Deliverables">
              <ul className="space-y-2">
                {mission.deliverables.map((deliverable, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-blue-400 flex-shrink-0" />
                    <span className="text-gray-600 dark:text-gray-300">{deliverable}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {/* Research Phases Section */}
          {hasResearchPhases && (
            <Section title="Research Phases">
              <ResearchPhases phases={mission.research_phases} />
            </Section>
          )}

          {/* Error Message Section */}
          {mission.error_message && (
            <Section title="Error">
              <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                <p className="text-red-600 dark:text-red-400">{mission.error_message}</p>
              </div>
            </Section>
          )}

          {/* Results Markdown Section */}
          {mission.result_markdown && (
            <Section title="Results">
              <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4 overflow-x-auto">
                <pre className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300 font-mono">
                  {mission.result_markdown}
                </pre>
              </div>
            </Section>
          )}

          {/* Result Links Section */}
          {(mission.result_document_ids.length > 0 || mission.result_report_id) && (
            <Section title="Result Artifacts">
              <ResultLinks
                documentIds={mission.result_document_ids}
                reportId={mission.result_report_id}
              />
            </Section>
          )}

          {/* Execution Timeline & Metadata Section */}
          <Section title="Execution">
            <ExecutionTimeline
              createdAt={mission.created_at}
              queuedAt={mission.queued_at}
              startedAt={mission.started_at}
              completedAt={mission.completed_at}
              executionMetadata={mission.execution_metadata}
            />

            {mission.deepsearch_job_id && (
              <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-3">
                  Job Details
                </h3>
                <div className="grid gap-4 sm:grid-cols-2 text-sm">
                  <div>
                    <p className="text-gray-500 dark:text-gray-400">DeepSearch Job ID</p>
                    <p className="font-mono text-gray-900 dark:text-white break-all">
                      {mission.deepsearch_job_id}
                    </p>
                  </div>
                  {mission.created_by && (
                    <div>
                      <p className="text-gray-500 dark:text-gray-400">Created By</p>
                      <p className="text-gray-900 dark:text-white">{mission.created_by}</p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}

export default function MissionDetailPage() {
  return (
    <AuthGate>
      <MissionDetailContent />
    </AuthGate>
  );
}
