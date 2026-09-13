import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { apiErrorMessage } from "@/lib/api/errors";
import { ContractPreviewPanel } from "./ContractPreviewPanel";
import { useForm, useWatch, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import useSWR from "swr";

import type { CollectionMissionSeed } from "@/lib/api/collections";
import { missionsApi } from "@/lib/api/missions";
import { projectsApi } from "@/lib/api/projects";
import {
  apiMissionFormSchema,
  defaultApiMissionFormValues,
  type ApiMissionFormValues,
} from "@/lib/schemas/apiMissionForm";
import type { ApiMission, ApiMissionCreate, ApiMissionUpdate, MissionContractPreview } from "@/types/mission";
import type { Project } from "@/types/document";
import { PageState } from "@/components/ui/PageState";
import { DynamicListInput } from "./DynamicListInput";

const SECTION_CLASS =
  "rounded-2xl border border-line bg-surface p-6 shadow-sm";

interface MissionFormProps {
  source?: ApiMission;
  seed?: CollectionMissionSeed;
  mode?: "create" | "edit";
  onSuccess?: (mission: ApiMission) => void;
  onCancel?: () => void;
}

type JsonFieldName =
  | "expected_output_schema"
  | "coverage_thresholds"
  | "validation_thresholds";

type JsonFieldState = Record<JsonFieldName, string>;
type JsonFieldErrors = Partial<Record<JsonFieldName, string>>;

const JSON_FIELD_LABELS: Record<JsonFieldName, string> = {
  expected_output_schema: "Expected output schema",
  coverage_thresholds: "Coverage thresholds",
  validation_thresholds: "Validation thresholds",
};

const JSON_FIELD_PLACEHOLDERS: Record<JsonFieldName, string> = {
  expected_output_schema:
    '{\n  "type": "object",\n  "properties": {\n    "summary": {"type": "string"}\n  }\n}',
  coverage_thresholds: '{\n  "min_sources": 12,\n  "min_per_required_entity": 2\n}',
  validation_thresholds: '{\n  "structural": 0.85,\n  "coverage": 0.70\n}',
};

/** Parse a JSON-textarea value. Returns undefined for empty, parsed object, or an error message. */
function parseJsonField(
  raw: string
): { value: Record<string, unknown> | undefined; error?: string } {
  const trimmed = raw.trim();
  if (!trimmed) return { value: undefined };
  try {
    const parsed = JSON.parse(trimmed);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return { value: undefined, error: "Must be a JSON object." };
    }
    return { value: parsed as Record<string, unknown> };
  } catch (err) {
    return { value: undefined, error: `Invalid JSON: ${(err as Error).message}` };
  }
}

/**
 * Form for creating a new DeepSearch mission.
 * Supports "Save and preview" and "Submit Immediately" actions.
 */
export function MissionForm({ onSuccess, onCancel, source, seed, mode = "create" }: MissionFormProps) {
  const { user } = useAuth();
  const [initialValues] = useState<ApiMissionFormValues>(() => {
    const authored = Object.fromEntries(Object.keys(apiMissionFormSchema.shape)
      .filter(key => source && source[key as keyof ApiMission] != null)
      .map(key => [key, source![key as keyof ApiMission]]));
    const priority = source?.metadata?.priority;
    return { ...defaultApiMissionFormValues, ...(seed ? { title: seed.title, project_id: seed.project_id ?? "", background: seed.background, references: seed.references, context: seed.context } : {}), ...authored, status: "draft",
      priority: priority === "low" || priority === "high" ? priority : "normal",
      mission_id: mode === "edit" ? source?.mission_id ?? "" : source ? `RUN-${crypto.randomUUID()}` : seed ? `COLL-${crypto.randomUUID()}` : "",
    } as ApiMissionFormValues;
  });
  const [saved, setSaved] = useState<ApiMission | null>(mode === "edit" ? source ?? null : null);
  const [preview, setPreview] = useState<MissionContractPreview | null>(null);
  const [previewRevision, setPreviewRevision] = useState(0);
  const [jsonDirty, setJsonDirty] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showProjectRequiredTooltip, setShowProjectRequiredTooltip] = useState(false);
  const [jsonFields, setJsonFields] = useState<JsonFieldState>({
    expected_output_schema: source?.expected_output_schema ? JSON.stringify(source.expected_output_schema, null, 2) : "",
    coverage_thresholds: source?.coverage_thresholds ? JSON.stringify(source.coverage_thresholds, null, 2) : "",
    validation_thresholds: source?.validation_thresholds ? JSON.stringify(source.validation_thresholds, null, 2) : "",
  });
  const [jsonErrors, setJsonErrors] = useState<JsonFieldErrors>({});
  const submitButtonRef = useRef<HTMLButtonElement>(null);

  // Fetch projects for dropdown
  const { data: projectsData, error: projectsError, mutate: reloadProjects } = useSWR<Project[]>(
    ["projects-list", user?.user_id],
    () => projectsApi.listAllProjects()
  );
  const projects = projectsData ?? [];

  const {
    control,
    register,
    handleSubmit,
    setError,
    clearErrors,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<ApiMissionFormValues>({
    defaultValues: initialValues,
    resolver: zodResolver(apiMissionFormSchema),
    mode: "onBlur",
  });

  // Watch project_id to enable/disable Submit button
  const projectId = useWatch({ control, name: "project_id" });
  const isProjectSelected = Boolean(projectId && projectId.trim() !== "");

  // Hide tooltip when clicking outside the submit button
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (submitButtonRef.current && !submitButtonRef.current.contains(event.target as Node)) {
        setShowProjectRequiredTooltip(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // T41.6: project_id is required at create for BOTH draft and queued.
  // Pre-T41.6 the draft path silently saved orphans (1.3% of stock at
  // sprint cutover); both buttons now share the same project gate.
  const handleDisabledSubmitClick = () => {
    setShowProjectRequiredTooltip(true);
    setSubmitError("A project must be selected before saving or submitting. Pick one from the dropdown above.");
  };

  const handleFormSubmit = async (
    values: ApiMissionFormValues,
    submitStatus: "draft" | "queued"
  ) => {
    setSubmitError(null);
    clearErrors();

    // Validate the three JSON textareas up-front; block submit if any is malformed.
    const parsedJson: Partial<Record<JsonFieldName, Record<string, unknown>>> = {};
    const nextJsonErrors: JsonFieldErrors = {};
    (Object.keys(jsonFields) as JsonFieldName[]).forEach((key) => {
      const { value, error } = parseJsonField(jsonFields[key]);
      if (error) nextJsonErrors[key] = error;
      if (value !== undefined) parsedJson[key] = value;
    });
    setJsonErrors(nextJsonErrors);
    if (Object.keys(nextJsonErrors).length > 0) {
      setSubmitError("Fix JSON errors in the Research Contract section before submitting.");
      return;
    }

    const references = (values.references ?? [])
      .map((ref) => (typeof ref === "string" ? { title: ref } : ref))
      .filter((ref) => ref && typeof ref.title === "string" && ref.title.trim() !== "");

    try {
      const payload: ApiMissionCreate = {
        mission_id: values.mission_id,
        title: values.title,
        objective: values.objective,
        success_criteria: values.success_criteria.filter((c) => c.trim() !== ""),
        project_id: values.project_id || undefined,
        deliverables: values.deliverables?.filter((d) => d.trim() !== "") || [],
        tags: values.tags?.filter((t) => t.trim() !== "") || [],
        metadata: {
          ...values.metadata,
          priority: values.priority,
        },
        status: "draft",
        context: values.context,
        research_phases: values.research_phases,
        // Empty optional fields explicitly clear an earlier saved draft value.
        background: values.background?.trim() || null,
        focus: values.focus?.trim() || null,
        references: references.length > 0 ? references : null,
        required_entities:
          values.required_entities && values.required_entities.filter((x) => x.trim() !== "").length > 0
            ? values.required_entities.filter((x) => x.trim() !== "")
            : null,
        excluded_entities:
          values.excluded_entities && values.excluded_entities.filter((x) => x.trim() !== "").length > 0
            ? values.excluded_entities.filter((x) => x.trim() !== "")
            : null,
        constraints:
          values.constraints && values.constraints.filter((x) => x.trim() !== "").length > 0
            ? values.constraints.filter((x) => x.trim() !== "")
            : null,
        deliverable_format: values.deliverable_format?.trim() || null,
        max_loops: values.max_loops ?? null,
        min_loops: values.min_loops ?? null,
        expected_output_schema: parsedJson.expected_output_schema ?? null,
        coverage_thresholds: parsedJson.coverage_thresholds ?? null,
        validation_thresholds: parsedJson.validation_thresholds ?? null,
      };

      // Save once; retry a failed preview/submit against this same draft.
      let mission: ApiMission;
      if (saved) {
        const latest = await missionsApi.get(saved.id);
        if (latest.status !== "draft") throw new Error(`This mission is already ${latest.status.replaceAll("_", " ")}. Open the saved mission to inspect it.`);
        const changes = Object.fromEntries(Object.entries(payload).filter(([key]) => key !== "mission_id" && key !== "status")) as ApiMissionUpdate;
        mission = await missionsApi.update(saved.id, changes);
      } else {
        mission = await missionsApi.create(payload);
      }
      setSaved(mission);
      reset(values);
      setJsonDirty(false);
      setPreview(null);
      if (submitStatus === "queued") {
        const submitted = await missionsApi.submitToDeepSearch(mission.id);
        onSuccess?.({ ...mission, status: submitted.status as ApiMission["status"] });
      } else {
        const compiled = await missionsApi.previewContract(mission.id);
        setPreview(compiled);
        setPreviewRevision(value => value + 1);
      }
    } catch (err) {
      setSubmitError(apiErrorMessage(err, "Mission could not be saved or submitted"));
      try {
        const detail = JSON.parse((err as Error).message).detail;
        const violations = Array.isArray(detail) ? detail : detail?.errors ?? [];
        if (typeof detail?.message === "string") setSubmitError(detail.message);
        for (const violation of violations) {
          const field = violation.field ?? violation.loc?.find((key: string) => key in apiMissionFormSchema.shape);
          const message = violation.message ?? violation.msg;
          if (field in apiMissionFormSchema.shape && typeof message === "string") {
            setError(field as keyof ApiMissionFormValues, { type: "server", message });
            if (field in JSON_FIELD_LABELS) setJsonErrors(previous => ({ ...previous, [field]: message }));
          }
        }
      } catch { /* Non-validation errors stay in the form-level alert. */ }
    }
  };

  const onSubmitDraft = handleSubmit((values) => handleFormSubmit(values, "draft"));
  const onSubmitQueued = handleSubmit((values) => handleFormSubmit(values, "queued"));

  return (
    <form className="space-y-6" onSubmit={event => event.preventDefault()}>
      {projectsError && <PageState state="error" title="Projects could not load." onRetry={() => void reloadProjects()} />}
      {/* Basic Information */}
      <section className={`${SECTION_CLASS} space-y-4`}>
        <header>
          <p className="text-xs uppercase tracking-widest text-muted">
            Required
          </p>
          <h2 className="text-xl font-semibold text-foreground">
            Mission Details
          </h2>
        </header>

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label htmlFor="mission-mission_id" className="form-label">
              Mission ID <span className="text-danger">*</span>
            </label>
            <input id="mission-mission_id"
              {...register("mission_id")}
              readOnly={Boolean(saved)}
              placeholder="e.g., M-2024-001"
              className="form-input"
            />
            {errors.mission_id && (
              <p className="form-error">{errors.mission_id.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="mission-title" className="form-label">
              Title <span className="text-danger">*</span>
            </label>
            <input id="mission-title"
              {...register("title")}
              placeholder="Mission title"
              className="form-input"
            />
            {errors.title && <p className="form-error">{errors.title.message}</p>}
          </div>
        </div>

        <div>
          <label htmlFor="mission-objective" className="form-label">
            Objective <span className="text-danger">*</span>
          </label>
          <textarea id="mission-objective"
            {...register("objective")}
            placeholder="Describe the mission goal and what you want to achieve..."
            className="form-input min-h-[100px]"
          />
          {errors.objective && (
            <p className="form-error">{errors.objective.message}</p>
          )}
        </div>

        <Controller
          control={control}
          name="success_criteria"
          render={({ field }) => (
            <DynamicListInput
              label="Success Criteria"
              items={field.value}
              onChange={field.onChange}
              placeholder="Define a measurable success criterion..."
              minItems={1}
              error={errors.success_criteria?.message || errors.success_criteria?.root?.message}
              required
            />
          )}
        />
      </section>

      {/* Project & Configuration */}
      <section className={`${SECTION_CLASS} space-y-4`}>
        <header>
          <p className="text-xs uppercase tracking-widest text-muted">
            Configuration
          </p>
          <h2 className="text-xl font-semibold text-foreground">
            Project & Settings
          </h2>
        </header>

        <div>
          <label htmlFor="mission-project_id" className="form-label">
            Project <span className="text-danger">*</span>
          </label>
          <select id="mission-project_id" {...register("project_id")} value={projectId ?? ""} className="form-input">
            <option value="">Select a project</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          {!isProjectSelected && (
            <p className="mt-1 text-xs text-warning">
              Required — missions must belong to a project
            </p>
          )}
          {errors.project_id && (
            <p className="form-error">{errors.project_id.message}</p>
          )}
        </div>

        <div>
          <label htmlFor="mission-priority" className="form-label">Priority</label>
          <select id="mission-priority" {...register("priority")} className="form-input">
            <option value="low">Low</option>
            <option value="normal">Normal</option>
            <option value="high">High</option>
          </select>
        </div>
      </section>

      {/* Research Contract — authoring fields consumed by DeepSearch */}
      <section className={`${SECTION_CLASS} space-y-4`}>
        <header>
          <p className="text-xs uppercase tracking-widest text-muted">
            Authoring Contract
          </p>
          <h2 className="text-xl font-semibold text-foreground">
            Research Contract
          </h2>
          <p className="mt-1 text-sm text-muted">
            Optional fields the DeepSearch contract compiler reads when shaping
            retrieval and synthesis. Skip any that don&apos;t apply.
          </p>
        </header>

        <div>
          <label htmlFor="mission-background" className="form-label">Background</label>
          <textarea id="mission-background"
            {...register("background")}
            placeholder="Free-form prose orienting the research (e.g., what prior work is this building on?)"
            className="form-input min-h-[80px]"
          />
          {errors.background && <p className="form-error">{errors.background.message}</p>}
        </div>

        <div>
          <label htmlFor="mission-focus" className="form-label">Focus</label>
          <textarea id="mission-focus"
            {...register("focus")}
            placeholder="Narrow framing for the research question"
            className="form-input min-h-[60px]"
          />
          {errors.focus && <p className="form-error">{errors.focus.message}</p>}
        </div>

        <Controller
          control={control}
          name="references"
          render={({ field }) => (
            <DynamicListInput
              label="References"
              items={(field.value ?? []).map((r) =>
                typeof r === "string" ? r : (r?.title ?? "")
              )}
              onChange={(_items, change) => {
                const references = field.value ?? [];
                if (change.kind === "add") field.onChange([...references, { title: "" }]);
                else if (change.kind === "remove") field.onChange(references.filter((_, index) => index !== change.index));
                else field.onChange(references.map((reference, index) => index === change.index ? { ...reference, title: change.value } : reference));
              }}
              error={errors.references?.message}
              placeholder="Seed reference title (e.g. 'Burns et al. 2022')"
              minItems={0}
            />
          )}
        />

        <Controller
          control={control}
          name="required_entities"
          render={({ field }) => (
            <DynamicListInput
              label="Required entities"
              items={field.value ?? []}
              onChange={field.onChange}
              placeholder="Entity that MUST appear in results..."
              error={errors.required_entities?.message}
              minItems={0}
            />
          )}
        />

        <Controller
          control={control}
          name="excluded_entities"
          render={({ field }) => (
            <DynamicListInput
              label="Excluded entities"
              items={field.value ?? []}
              onChange={field.onChange}
              placeholder="Entity that MUST NOT appear in results..."
              error={errors.excluded_entities?.message}
              minItems={0}
            />
          )}
        />

        <Controller
          control={control}
          name="constraints"
          render={({ field }) => (
            <DynamicListInput
              label="Constraints"
              items={field.value ?? []}
              onChange={field.onChange}
              placeholder="Add a constraint (e.g. 'no paywalled sources')..."
              error={errors.constraints?.message}
              minItems={0}
            />
          )}
        />

        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <label htmlFor="mission-deliverable_format" className="form-label">Deliverable format</label>
            <input id="mission-deliverable_format"
              {...register("deliverable_format")}
              placeholder="e.g. markdown report, comparison table"
              className="form-input"
            />
            {errors.deliverable_format && <p className="form-error">{errors.deliverable_format.message}</p>}
        </div>
          <div>
            <label htmlFor="mission-min_loops" className="form-label">Min loops</label>
            <input id="mission-min_loops"
              type="number"
              min={1}
              max={50}
              {...register("min_loops", { setValueAs: value => value === "" ? undefined : Number(value) })}
              className="form-input"
            />
            {errors.min_loops && (
              <p className="form-error">{errors.min_loops.message}</p>
            )}
          </div>
          <div>
            <label htmlFor="mission-max_loops" className="form-label">Max loops</label>
            <input id="mission-max_loops"
              type="number"
              min={1}
              max={50}
              {...register("max_loops", { setValueAs: value => value === "" ? undefined : Number(value) })}
              className="form-input"
            />
            {errors.max_loops && (
              <p className="form-error">{errors.max_loops.message}</p>
            )}
          </div>
        </div>

        {/* JSON-shaped fields */}
        {(Object.keys(JSON_FIELD_LABELS) as JsonFieldName[]).map((key) => (
          <div key={key}>
            <label htmlFor={`mission-${key}`} className="form-label">{JSON_FIELD_LABELS[key]}</label>
            <textarea id={`mission-${key}`}
              value={jsonFields[key]}
              onChange={(e) => {
                setJsonFields((prev) => ({ ...prev, [key]: e.target.value }));
                setJsonDirty(true);
                if (jsonErrors[key]) {
                  setJsonErrors((prev) => {
                    const next = { ...prev };
                    delete next[key];
                    return next;
                  });
                }
              }}
              placeholder={JSON_FIELD_PLACEHOLDERS[key]}
              className="form-input min-h-[100px] font-mono text-sm"
            />
            {jsonErrors[key] && (
              <p className="form-error">{jsonErrors[key]}</p>
            )}
          </div>
        ))}
      </section>

      {/* Deliverables & Tags */}
      <section className={`${SECTION_CLASS} space-y-4`}>
        <header>
          <p className="text-xs uppercase tracking-widest text-muted">
            Optional
          </p>
          <h2 className="text-xl font-semibold text-foreground">
            Deliverables & Tags
          </h2>
        </header>

        <Controller
          control={control}
          name="deliverables"
          render={({ field }) => (
            <DynamicListInput
              label="Deliverables"
              items={field.value ?? []}
              onChange={field.onChange}
              placeholder="Define an expected deliverable..."
              error={errors.deliverables?.message}
              minItems={0}
            />
          )}
        />

        <Controller
          control={control}
          name="tags"
          render={({ field }) => (
            <DynamicListInput
              label="Tags"
              items={field.value ?? []}
              onChange={field.onChange}
              placeholder="Add a tag..."
              error={errors.tags?.message}
              minItems={0}
            />
          )}
        />
      </section>

      {saved && <section className="space-y-3" aria-label="Saved draft preview">
        <p className="text-sm text-secondary">Draft saved. <Link className="underline" href={`/missions/${saved.id}`}>Open saved draft</Link></p>
        {(isDirty || jsonDirty) && <p role="status" className="text-sm text-warning">Unsaved changes — save again to update the preview.</p>}
        {preview && <ContractPreviewPanel key={previewRevision} missionId={saved.id} initialPreview={preview} />}
      </section>}

      {/* Error Display */}
      {submitError && (
        <div role="alert" className="p-4 bg-danger-surface border border-danger-line rounded-lg">
          <p className="text-sm text-danger">{submitError}</p>
        </div>
      )}

      {/* Actions */}
      <section className={`${SECTION_CLASS}`}>
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-between">
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2.5 text-sm font-medium text-secondary hover:bg-surface rounded-lg transition-colors"
            >
              {mode === "edit" ? "Close editor" : "Back to missions"}
            </button>
          )}

          <div className="flex flex-wrap gap-3 sm:ml-auto">
            <button
              type="button"
              onClick={isProjectSelected ? onSubmitDraft : handleDisabledSubmitClick}
              disabled={isSubmitting}
              className={`px-4 py-2.5 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 ${
                isProjectSelected
                  ? "text-secondary bg-surface hover:bg-surface-alt"
                  : "text-muted bg-surface-alt cursor-not-allowed"
              }`}
              title={isProjectSelected ? undefined : "Select a project to save"}
            >
              {isSubmitting ? "Saving..." : "Save and preview"}
            </button>

            <div className="relative">
              <button
                ref={submitButtonRef}
                type="button"
                onClick={isProjectSelected ? onSubmitQueued : handleDisabledSubmitClick}
                disabled={isSubmitting}
                className={`px-4 py-2.5 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 ${
                  isProjectSelected
                    ? "text-on-accent bg-accent hover:bg-accent"
                    : "text-muted bg-surface-alt cursor-not-allowed"
                }`}
                title={isProjectSelected ? undefined : "Select a project to submit to DeepSearch"}
              >
                {isSubmitting ? "Submitting..." : "Submit to DeepSearch"}
              </button>
              {showProjectRequiredTooltip && !isProjectSelected && (
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-background text-foreground text-xs rounded-lg w-52 max-w-full shadow-lg z-10">
                  Select a project to submit to DeepSearch
                  <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-line-strong" />
                </div>
              )}
            </div>
          </div>
        </div>
      </section>
    </form>
  );
}
