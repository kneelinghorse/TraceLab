import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { formatDistanceToNow } from "date-fns";

import { AuthGate } from "@/components/AuthGate";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { ContractPreviewPanel, ExecutionTimeline, ResearchPhases, ResultLinks } from "@/components/missions";
import { downloadFile } from "@/lib/api/console";
import { missionsApi } from "@/lib/api/missions";
import { useApiMission } from "@/lib/hooks/useMissions";
import type { MissionStatus, ReportPromotionResponse, ApiMissionUpdate } from "@/types/mission";

const STATUS_COLORS: Record<MissionStatus, { bg: string; text: string; dot: string }> = {
  draft: { bg: "bg-surface dark:bg-surface-alt", text: "text-secondary dark:text-secondary", dot: "bg-surface-alt" },
  queued: { bg: "bg-warning-surface dark:bg-warning-surface", text: "text-warning dark:text-warning", dot: "bg-warning" },
  in_progress: { bg: "bg-info-surface dark:bg-info-surface", text: "text-accent-text dark:text-accent-text", dot: "bg-accent" },
  completed: { bg: "bg-success-surface dark:bg-success-surface", text: "text-success dark:text-success", dot: "bg-success" },
  blocked: { bg: "bg-danger-surface dark:bg-danger-surface", text: "text-danger dark:text-danger", dot: "bg-danger" },
  cancelled: { bg: "bg-surface dark:bg-surface-alt", text: "text-muted dark:text-muted", dot: "bg-surface-alt" },
  validation_failed: { bg: "bg-warning-surface dark:bg-warning-surface", text: "text-warning dark:text-warning", dot: "bg-warning" },
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
    <div className="p-6 border-b border-line dark:border-line last:border-b-0">
      <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">{title}</h2>
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

  // Authoring fields (T40.2) — string-form for prose/ints, arrays for lists, raw
  // JSON strings for the three structured fields so mid-edit invalid JSON
  // doesn't wipe the draft.
  const [editBackground, setEditBackground] = useState("");
  const [editFocus, setEditFocus] = useState("");
  const [editReferences, setEditReferences] = useState<string[]>([]);
  const [editRequiredEntities, setEditRequiredEntities] = useState<string[]>([]);
  const [editExcludedEntities, setEditExcludedEntities] = useState<string[]>([]);
  const [editConstraints, setEditConstraints] = useState<string[]>([]);
  const [editDeliverableFormat, setEditDeliverableFormat] = useState("");
  const [editMaxLoops, setEditMaxLoops] = useState<string>("");
  const [editMinLoops, setEditMinLoops] = useState<string>("");
  const [editExpectedOutputSchema, setEditExpectedOutputSchema] = useState("");
  const [editCoverageThresholds, setEditCoverageThresholds] = useState("");
  const [editValidationThresholds, setEditValidationThresholds] = useState("");
  const [editJsonErrors, setEditJsonErrors] = useState<{
    expected_output_schema?: string;
    coverage_thresholds?: string;
    validation_thresholds?: string;
  }>({});

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
    // Hydrate authoring fields from the current mission.
    setEditBackground(mission.background ?? "");
    setEditFocus(mission.focus ?? "");
    setEditReferences((mission.references ?? []).map((r) => r?.title ?? ""));
    setEditRequiredEntities([...(mission.required_entities ?? [])]);
    setEditExcludedEntities([...(mission.excluded_entities ?? [])]);
    setEditConstraints([...(mission.constraints ?? [])]);
    setEditDeliverableFormat(mission.deliverable_format ?? "");
    setEditMaxLoops(mission.max_loops != null ? String(mission.max_loops) : "");
    setEditMinLoops(mission.min_loops != null ? String(mission.min_loops) : "");
    setEditExpectedOutputSchema(
      mission.expected_output_schema ? JSON.stringify(mission.expected_output_schema, null, 2) : ""
    );
    setEditCoverageThresholds(
      mission.coverage_thresholds ? JSON.stringify(mission.coverage_thresholds, null, 2) : ""
    );
    setEditValidationThresholds(
      mission.validation_thresholds ? JSON.stringify(mission.validation_thresholds, null, 2) : ""
    );
    setEditJsonErrors({});
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

    // Parse the three JSON authoring fields. Invalid JSON blocks the save and
    // surfaces inline errors without losing the user's draft.
    const parseJson = (raw: string): { value?: Record<string, unknown>; error?: string } => {
      const trimmed = raw.trim();
      if (!trimmed) return {};
      try {
        const parsed = JSON.parse(trimmed);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          return { error: "Must be a JSON object." };
        }
        return { value: parsed as Record<string, unknown> };
      } catch (err) {
        return { error: `Invalid JSON: ${(err as Error).message}` };
      }
    };

    const schemaParse = parseJson(editExpectedOutputSchema);
    const coverageParse = parseJson(editCoverageThresholds);
    const validationParse = parseJson(editValidationThresholds);

    const jsonErrs: typeof editJsonErrors = {};
    if (schemaParse.error) jsonErrs.expected_output_schema = schemaParse.error;
    if (coverageParse.error) jsonErrs.coverage_thresholds = coverageParse.error;
    if (validationParse.error) jsonErrs.validation_thresholds = validationParse.error;
    setEditJsonErrors(jsonErrs);
    if (Object.keys(jsonErrs).length > 0) {
      setEditError("Fix JSON errors below before saving.");
      return;
    }

    const parseLoopBound = (raw: string): number | undefined => {
      const trimmed = raw.trim();
      if (!trimmed) return undefined;
      const n = Number(trimmed);
      return Number.isInteger(n) && n >= 1 ? n : undefined;
    };

    setIsSaving(true);

    try {
      const references = editReferences
        .map((title) => title.trim())
        .filter((title) => title !== "")
        .map((title) => ({ title }));

      const updateData: ApiMissionUpdate = {
        title: editTitle.trim(),
        objective: editObjective.trim(),
        success_criteria: editSuccessCriteria.filter(c => c.trim() !== ""),
        deliverables: editDeliverables.filter(d => d.trim() !== ""),
        tags: editTags.filter(t => t.trim() !== ""),
        background: editBackground.trim() || null,
        focus: editFocus.trim() || null,
        references: references.length > 0 ? references : null,
        required_entities:
          editRequiredEntities.filter((x) => x.trim() !== "").length > 0
            ? editRequiredEntities.filter((x) => x.trim() !== "")
            : null,
        excluded_entities:
          editExcludedEntities.filter((x) => x.trim() !== "").length > 0
            ? editExcludedEntities.filter((x) => x.trim() !== "")
            : null,
        constraints:
          editConstraints.filter((x) => x.trim() !== "").length > 0
            ? editConstraints.filter((x) => x.trim() !== "")
            : null,
        deliverable_format: editDeliverableFormat.trim() || null,
        max_loops: parseLoopBound(editMaxLoops) ?? null,
        min_loops: parseLoopBound(editMinLoops) ?? null,
        expected_output_schema: schemaParse.value ?? null,
        coverage_thresholds: coverageParse.value ?? null,
        validation_thresholds: validationParse.value ?? null,
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
      <div className="min-h-screen bg-background dark:bg-background py-8">
        <div className="max-w-4xl mx-auto px-4">
          <p className="text-secondary dark:text-muted">Select a mission to view details.</p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background dark:bg-background py-8">
        <div className="max-w-4xl mx-auto px-4">
          <p className="text-secondary dark:text-muted">Loading mission...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-background dark:bg-background py-8">
        <div className="max-w-4xl mx-auto px-4">
          <div className="bg-danger-surface dark:bg-danger-surface border border-danger-line dark:border-danger-line rounded-lg p-6">
            <p className="text-danger dark:text-danger">
              Failed to load mission: {error.message}
            </p>
            <button
              onClick={refresh}
              className="mt-2 text-sm font-medium text-danger dark:text-danger underline"
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
      <div className="min-h-screen bg-background dark:bg-background py-8">
        <div className="max-w-4xl mx-auto px-4">
          <p className="text-secondary dark:text-muted">Mission not found.</p>
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
    <div className="min-h-screen bg-background dark:bg-background py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-6 flex items-center justify-between">
          <Link
            href="/missions"
            className="inline-flex items-center text-sm text-accent-text dark:text-accent-text hover:text-accent-text"
          >
            &larr; Back to missions
          </Link>
          <div className="flex items-center gap-2">
            <button
              onClick={refresh}
              className="px-3 py-1.5 text-sm text-secondary dark:text-muted hover:text-foreground dark:hover:text-foreground border border-line-strong dark:border-line-strong rounded-lg"
            >
              Refresh
            </button>
          </div>
        </div>

        <div className="bg-surface dark:bg-surface border border-line dark:border-line rounded-lg overflow-hidden">
          {/* Header Section */}
          <div className="p-6 border-b border-line dark:border-line">
            {isEditing ? (
              /* Edit Mode Form */
              <div className="space-y-6">
                <div className="flex items-center gap-3 mb-4">
                  <StatusBadge status={mission.status} />
                  <span className="text-sm font-mono text-muted dark:text-muted">
                    {mission.mission_id}
                  </span>
                  <span className="px-2 py-1 text-xs bg-info-surface dark:bg-info-surface text-accent-text dark:text-accent-text rounded">
                    Editing
                  </span>
                </div>

                {/* Title */}
                <div>
                  <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">
                    Title *
                  </label>
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full px-4 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground focus:ring-2 focus:ring-focus focus:border-transparent"
                    autoFocus
                  />
                </div>

                {/* Objective */}
                <div>
                  <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">
                    Objective *
                  </label>
                  <textarea
                    value={editObjective}
                    onChange={(e) => setEditObjective(e.target.value)}
                    rows={3}
                    className="w-full px-4 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground focus:ring-2 focus:ring-focus focus:border-transparent"
                  />
                </div>

                {/* Success Criteria */}
                <div>
                  <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">
                    Success Criteria
                  </label>
                  <div className="space-y-2">
                    {editSuccessCriteria.map((criterion, index) => (
                      <div key={index} className="flex gap-2">
                        <input
                          type="text"
                          value={criterion}
                          onChange={(e) => handleUpdateListItem(setEditSuccessCriteria, index, e.target.value)}
                          className="flex-1 px-3 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground text-sm"
                          placeholder="Enter success criterion"
                        />
                        <button
                          type="button"
                          onClick={() => handleRemoveListItem(setEditSuccessCriteria, index)}
                          className="px-3 py-2 text-danger dark:text-danger hover:bg-danger-surface dark:hover:bg-danger-surface rounded-lg"
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() => handleAddListItem(setEditSuccessCriteria)}
                      className="px-3 py-2 text-sm text-accent-text dark:text-accent-text hover:bg-info-surface dark:hover:bg-info-surface rounded-lg"
                    >
                      + Add Criterion
                    </button>
                  </div>
                </div>

                {/* Deliverables */}
                <div>
                  <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">
                    Deliverables
                  </label>
                  <div className="space-y-2">
                    {editDeliverables.map((deliverable, index) => (
                      <div key={index} className="flex gap-2">
                        <input
                          type="text"
                          value={deliverable}
                          onChange={(e) => handleUpdateListItem(setEditDeliverables, index, e.target.value)}
                          className="flex-1 px-3 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground text-sm"
                          placeholder="Enter deliverable"
                        />
                        <button
                          type="button"
                          onClick={() => handleRemoveListItem(setEditDeliverables, index)}
                          className="px-3 py-2 text-danger dark:text-danger hover:bg-danger-surface dark:hover:bg-danger-surface rounded-lg"
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() => handleAddListItem(setEditDeliverables)}
                      className="px-3 py-2 text-sm text-accent-text dark:text-accent-text hover:bg-info-surface dark:hover:bg-info-surface rounded-lg"
                    >
                      + Add Deliverable
                    </button>
                  </div>
                </div>

                {/* Tags */}
                <div>
                  <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">
                    Tags
                  </label>
                  <div className="space-y-2">
                    {editTags.map((tag, index) => (
                      <div key={index} className="flex gap-2">
                        <input
                          type="text"
                          value={tag}
                          onChange={(e) => handleUpdateListItem(setEditTags, index, e.target.value)}
                          className="flex-1 px-3 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground text-sm"
                          placeholder="Enter tag"
                        />
                        <button
                          type="button"
                          onClick={() => handleRemoveListItem(setEditTags, index)}
                          className="px-3 py-2 text-danger dark:text-danger hover:bg-danger-surface dark:hover:bg-danger-surface rounded-lg"
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() => handleAddListItem(setEditTags)}
                      className="px-3 py-2 text-sm text-accent-text dark:text-accent-text hover:bg-info-surface dark:hover:bg-info-surface rounded-lg"
                    >
                      + Add Tag
                    </button>
                  </div>
                </div>

                {/* Research Contract — authoring fields (T40.2) */}
                <details className="rounded-lg border border-line dark:border-line bg-background dark:bg-background">
                  <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-foreground dark:text-secondary">
                    Research Contract (optional — DeepSearch authoring fields)
                  </summary>
                  <div className="p-4 space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">Background</label>
                      <textarea
                        value={editBackground}
                        onChange={(e) => setEditBackground(e.target.value)}
                        className="w-full px-3 py-2 min-h-[70px] border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground"
                        placeholder="Free-form prose orienting the research"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">Focus</label>
                      <textarea
                        value={editFocus}
                        onChange={(e) => setEditFocus(e.target.value)}
                        className="w-full px-3 py-2 min-h-[60px] border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground"
                        placeholder="Narrow framing for the research question"
                      />
                    </div>
                    {([
                      { label: "References (one title per line)", value: editReferences, setter: setEditReferences, placeholder: "Reference title..." },
                      { label: "Required entities", value: editRequiredEntities, setter: setEditRequiredEntities, placeholder: "Entity that MUST appear..." },
                      { label: "Excluded entities", value: editExcludedEntities, setter: setEditExcludedEntities, placeholder: "Entity that MUST NOT appear..." },
                      { label: "Constraints", value: editConstraints, setter: setEditConstraints, placeholder: "Constraint (e.g. 'no paywalled sources')..." },
                    ] as const).map(({ label, value, setter, placeholder }) => (
                      <div key={label}>
                        <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">{label}</label>
                        <textarea
                          value={value.join("\n")}
                          onChange={(e) => setter(e.target.value.split("\n"))}
                          className="w-full px-3 py-2 min-h-[70px] border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground font-mono text-xs"
                          placeholder={placeholder}
                        />
                      </div>
                    ))}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">Deliverable format</label>
                        <input
                          type="text"
                          value={editDeliverableFormat}
                          onChange={(e) => setEditDeliverableFormat(e.target.value)}
                          className="w-full px-3 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground"
                          placeholder="e.g. markdown report"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">Min loops</label>
                        <input
                          type="number"
                          min={1}
                          value={editMinLoops}
                          onChange={(e) => setEditMinLoops(e.target.value)}
                          className="w-full px-3 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">Max loops</label>
                        <input
                          type="number"
                          min={1}
                          value={editMaxLoops}
                          onChange={(e) => setEditMaxLoops(e.target.value)}
                          className="w-full px-3 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground"
                        />
                      </div>
                    </div>
                    {([
                      { key: "expected_output_schema" as const, label: "Expected output schema (JSON object)", value: editExpectedOutputSchema, setter: setEditExpectedOutputSchema },
                      { key: "coverage_thresholds" as const, label: "Coverage thresholds (JSON object)", value: editCoverageThresholds, setter: setEditCoverageThresholds },
                      { key: "validation_thresholds" as const, label: "Validation thresholds (JSON object)", value: editValidationThresholds, setter: setEditValidationThresholds },
                    ]).map(({ key, label, value, setter }) => (
                      <div key={key}>
                        <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">{label}</label>
                        <textarea
                          value={value}
                          onChange={(e) => {
                            setter(e.target.value);
                            if (editJsonErrors[key]) {
                              setEditJsonErrors((prev) => {
                                const next = { ...prev };
                                delete next[key];
                                return next;
                              });
                            }
                          }}
                          className="w-full px-3 py-2 min-h-[100px] border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-surface-alt text-foreground dark:text-foreground font-mono text-xs"
                          placeholder='{"key": "value"}'
                        />
                        {editJsonErrors[key] && (
                          <p className="mt-1 text-xs text-danger dark:text-danger">{editJsonErrors[key]}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </details>

                {/* Error Display */}
                {editError && (
                  <p className="text-sm text-danger dark:text-danger">{editError}</p>
                )}

                {/* Save/Cancel Buttons */}
                <div className="flex gap-3 pt-2">
                  <button
                    onClick={handleSaveEdit}
                    disabled={isSaving}
                    className="px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
                  >
                    {isSaving ? "Saving..." : "Save Changes"}
                  </button>
                  <button
                    onClick={handleCancelEdit}
                    disabled={isSaving}
                    className="px-4 py-2 text-secondary dark:text-muted hover:text-foreground dark:hover:text-foreground transition-colors"
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
                      <span className="text-sm font-mono text-muted dark:text-muted">
                        {mission.mission_id}
                      </span>
                    </div>
                    <h1 className="text-2xl font-bold text-foreground dark:text-foreground">
                      {mission.title}
                    </h1>
                    <div className="mt-1 flex items-center gap-3 text-sm text-muted dark:text-muted">
                      {mission.project_id && mission.project_name ? (
                        <Link
                          href={`/projects/${mission.project_id}`}
                          className="text-accent-text dark:text-accent-text underline underline-offset-4"
                        >
                          {mission.project_name}
                        </Link>
                      ) : mission.project_id ? (
                        <Link
                          href={`/projects/${mission.project_id}`}
                          className="text-accent-text dark:text-accent-text underline underline-offset-4"
                        >
                          View Project
                        </Link>
                      ) : (
                        <span className="text-muted dark:text-muted">No project</span>
                      )}
                      {createdAt && (
                        <>
                          <span className="text-secondary dark:text-secondary">&bull;</span>
                          <span>Created {createdAt}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                {/* Tags */}
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  {mission.tags.map((tag) => (
                    <span
                      key={tag}
                      className="px-2 py-1 text-xs bg-surface dark:bg-surface-alt text-secondary dark:text-secondary rounded"
                    >
                      {tag}
                    </span>
                  ))}
                </div>

                {/* Action Buttons */}
                <div className="mt-6 flex flex-wrap gap-3">
                  {isDraft && (
                    <button
                      onClick={handleSubmitToDeepSearch}
                      disabled={isSubmitting}
                      className="px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium text-sm"
                    >
                      {isSubmitting ? "Submitting..." : "Submit to DeepSearch"}
                    </button>
                  )}
                  {mission.status === "completed" && (mission.result_report_id || mission.result_markdown) && !promotionResult && mission.result_document_ids.length === 0 && (
                    <button
                      onClick={handlePromoteReport}
                      disabled={isPromoting}
                      className="px-4 py-2 bg-success-surface text-success rounded-lg hover:bg-success-surface disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium text-sm"
                    >
                      {isPromoting ? "Promoting..." : "Promote to Document"}
                    </button>
                  )}
                  {promotionResult && (
                    <Link
                      href={`/documents/${promotionResult.document_id}`}
                      className="px-4 py-2 bg-success-surface dark:bg-success-surface text-success dark:text-success rounded-lg hover:bg-success-surface dark:hover:bg-success-surface transition-colors font-medium text-sm"
                    >
                      View Promoted Document
                    </Link>
                  )}
                  {!promotionResult && mission.result_document_ids.length > 0 && (
                    <Link
                      href={`/documents/${mission.result_document_ids[0]}`}
                      className="px-4 py-2 bg-success-surface dark:bg-success-surface text-success dark:text-success rounded-lg hover:bg-success-surface dark:hover:bg-success-surface transition-colors font-medium text-sm"
                    >
                      View Promoted Document
                    </Link>
                  )}
                  <button
                    onClick={handleStartEdit}
                    className="px-4 py-2 border border-line-strong dark:border-line-strong text-secondary dark:text-secondary rounded-lg hover:bg-background dark:hover:bg-surface-alt transition-colors font-medium text-sm"
                  >
                    Edit Mission
                  </button>
                  <button
                    onClick={handleDelete}
                    className="px-4 py-2 border border-danger-line dark:border-danger-line text-danger dark:text-danger rounded-lg hover:bg-danger-surface dark:hover:bg-danger-surface transition-colors font-medium text-sm"
                  >
                    Delete
                  </button>
                </div>
              </>
            )}

            {submitError && (
              <p className="mt-3 text-sm text-danger dark:text-danger">{submitError}</p>
            )}
            {promotionError && (
              <p className="mt-3 text-sm text-danger dark:text-danger">{promotionError}</p>
            )}
            {promotionResult && (
              <p className="mt-3 text-sm text-success dark:text-success">
                {promotionResult.message}
                {promotionResult.chunk_count !== null && ` (${promotionResult.chunk_count} chunks created)`}
              </p>
            )}
          </div>

          {/* Objective Section */}
          <Section title="Objective">
            <p className="text-secondary dark:text-secondary whitespace-pre-wrap">
              {mission.objective}
            </p>
          </Section>

          {/* Success Criteria Section */}
          {mission.success_criteria.length > 0 && (
            <Section title="Success Criteria">
              <ul className="space-y-2">
                {mission.success_criteria.map((criterion, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-surface-alt flex-shrink-0" />
                    <span className="text-secondary dark:text-secondary">{criterion}</span>
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
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-accent flex-shrink-0" />
                    <span className="text-secondary dark:text-secondary">{deliverable}</span>
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
              <div className="bg-danger-surface dark:bg-danger-surface border border-danger-line dark:border-danger-line rounded-lg p-4">
                <p className="text-danger dark:text-danger">{mission.error_message}</p>
              </div>
            </Section>
          )}

          {/* Results Markdown Section */}
          {mission.result_markdown && (
            <Section title="Results">
              <div className="flex justify-end mb-2">
                <button
                  onClick={() => downloadFile(
                    mission.result_markdown!,
                    `${mission.mission_id}-results.md`,
                    "text/markdown"
                  )}
                  className="px-3 py-1.5 text-xs font-medium text-accent-text dark:text-accent-text hover:bg-info-surface dark:hover:bg-surface-alt rounded transition-colors"
                >
                  Export as .md
                </button>
              </div>
              <div className="bg-background dark:bg-background rounded-lg p-4 overflow-x-auto">
                <MarkdownRenderer content={mission.result_markdown} />
              </div>
            </Section>
          )}

          {/* Contract Preview Panel (T40.4) */}
          {missionId && (
            <div className="p-6 border-b border-line dark:border-line">
              <ContractPreviewPanel missionId={missionId} />
            </div>
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
              reportMetadata={mission.result_protocol?.report_metadata}
            />

            {mission.deepsearch_job_id && (
              <div className="mt-6 pt-6 border-t border-line dark:border-line">
                <h3 className="text-sm font-semibold text-secondary dark:text-secondary uppercase tracking-wide mb-3">
                  Job Details
                </h3>
                <div className="grid gap-4 sm:grid-cols-2 text-sm">
                  <div>
                    <p className="text-muted dark:text-muted">DeepSearch Job ID</p>
                    <p className="font-mono text-foreground dark:text-foreground break-all">
                      {mission.deepsearch_job_id}
                    </p>
                  </div>
                  {mission.created_by && (
                    <div>
                      <p className="text-muted dark:text-muted">Created By</p>
                      <p className="text-foreground dark:text-foreground">{mission.created_by}</p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </Section>

          {/* Runner logs */}
          {missionId && <MissionLogTail missionId={missionId} status={mission?.status} />}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Log tail component — polls while mission is active, shows last N lines
// ---------------------------------------------------------------------------

type LogEntry = {
  id: string;
  level: string;
  message: string;
  source: string | null;
  logged_at: string;
};

const ACTIVE_STATUSES = new Set(["queued", "in_progress"]);
const POLL_INTERVAL_MS = 5000;
const LOG_LEVEL_COLORS: Record<string, string> = {
  ERROR: "text-danger dark:text-danger",
  WARNING: "text-warning dark:text-warning",
  WARN: "text-warning dark:text-warning",
  INFO: "text-secondary dark:text-muted",
  DEBUG: "text-muted dark:text-muted",
};

function MissionLogTail({ missionId, status }: { missionId: string; status: MissionStatus | undefined }) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [hasLogs, setHasLogs] = useState<boolean | null>(null); // null = not yet checked
  const bottomRef = useRef<HTMLDivElement>(null);
  const isActive = status ? ACTIVE_STATUSES.has(status) : false;

  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/v1/missions/${missionId}/logs?limit=100`,
        {
          headers: {
            Authorization: `Bearer ${typeof window !== "undefined" ? JSON.parse(localStorage.getItem("tracelab_auth") ?? "{}").token ?? "" : ""}`,
          },
        }
      );
      if (!res.ok) return;
      const data: LogEntry[] = await res.json();
      setLogs(data);
      if (hasLogs === null) setHasLogs(data.length > 0);
    } catch {
      // non-fatal
    }
  }, [missionId, hasLogs]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    if (!isActive) return;
    const id = setInterval(fetchLogs, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [isActive, fetchLogs]);

  // Auto-scroll to bottom when new logs arrive while active
  useEffect(() => {
    if (isActive && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, isActive]);

  // Don't render if we've confirmed there are no logs
  if (hasLogs === false && !isActive) return null;

  return (
    <div className="border-t border-line dark:border-line mt-0">
      <div className="p-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-foreground dark:text-foreground">
            Runner Logs
          </h2>
          {isActive && (
            <span className="flex items-center gap-1.5 text-xs text-accent-text dark:text-accent-text">
              <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
              Live
            </span>
          )}
        </div>

        {logs.length === 0 ? (
          <p className="text-sm text-muted dark:text-muted font-mono">
            {isActive ? "Waiting for logs..." : "No logs recorded."}
          </p>
        ) : (
          <div tabIndex={0} role="region" aria-label="Execution log" className="bg-background dark:bg-background rounded-lg p-4 overflow-y-auto max-h-96 font-mono text-xs space-y-0.5">
            {logs.map((log) => (
              <div key={log.id} className="flex gap-3 leading-5">
                <span className="shrink-0 text-muted dark:text-secondary w-[180px]">
                  {new Date(log.logged_at).toISOString().replace("T", " ").slice(0, 19)}
                </span>
                <span className={`shrink-0 w-14 ${LOG_LEVEL_COLORS[log.level] ?? LOG_LEVEL_COLORS.INFO}`}>
                  {log.level}
                </span>
                {log.source && (
                  <span className="shrink-0 text-muted dark:text-secondary max-w-[120px] truncate">
                    {log.source}
                  </span>
                )}
                <span className="text-secondary dark:text-foreground break-words min-w-0">
                  {log.message}
                </span>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
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
