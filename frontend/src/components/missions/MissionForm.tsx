import { useState, useRef, useEffect } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import useSWR from "swr";

import { missionsApi } from "@/lib/api/missions";
import { projectsApi } from "@/lib/api/projects";
import {
  apiMissionFormSchema,
  defaultApiMissionFormValues,
  type ApiMissionFormValues,
} from "@/lib/schemas/apiMissionForm";
import type { ApiMission, ApiMissionCreate } from "@/types/mission";
import type { Project } from "@/types/document";
import type { PaginatedResponse } from "@/types/pagination";
import { DynamicListInput } from "./DynamicListInput";

const SECTION_CLASS =
  "rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 shadow-sm";

interface MissionFormProps {
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
 * Supports "Save as Draft" and "Submit Immediately" actions.
 */
export function MissionForm({ onSuccess, onCancel }: MissionFormProps) {
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showProjectRequiredTooltip, setShowProjectRequiredTooltip] = useState(false);
  const [jsonFields, setJsonFields] = useState<JsonFieldState>({
    expected_output_schema: "",
    coverage_thresholds: "",
    validation_thresholds: "",
  });
  const [jsonErrors, setJsonErrors] = useState<JsonFieldErrors>({});
  const submitButtonRef = useRef<HTMLButtonElement>(null);

  // Fetch projects for dropdown
  const { data: projectsData } = useSWR<PaginatedResponse<Project>>(
    ["projects-list"],
    () => projectsApi.listProjects({ page: 1, pageSize: 100 })
  );
  const projects = projectsData?.data ?? [];

  const {
    control,
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ApiMissionFormValues>({
    defaultValues: defaultApiMissionFormValues,
    resolver: zodResolver(apiMissionFormSchema),
    mode: "onBlur",
  });

  // Watch project_id to enable/disable Submit button
  const projectId = watch("project_id");
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
          priority: values.priority,
          ...values.metadata,
        },
        research_depth: values.research_depth || "baseline",
        status: submitStatus,
        // Authoring fields — send only those the author actually filled in.
        background: values.background?.trim() || undefined,
        focus: values.focus?.trim() || undefined,
        references: references.length > 0 ? references : undefined,
        required_entities:
          values.required_entities && values.required_entities.filter((x) => x.trim() !== "").length > 0
            ? values.required_entities.filter((x) => x.trim() !== "")
            : undefined,
        excluded_entities:
          values.excluded_entities && values.excluded_entities.filter((x) => x.trim() !== "").length > 0
            ? values.excluded_entities.filter((x) => x.trim() !== "")
            : undefined,
        constraints:
          values.constraints && values.constraints.filter((x) => x.trim() !== "").length > 0
            ? values.constraints.filter((x) => x.trim() !== "")
            : undefined,
        deliverable_format: values.deliverable_format?.trim() || undefined,
        max_loops: values.max_loops,
        min_loops: values.min_loops,
        expected_output_schema: parsedJson.expected_output_schema,
        coverage_thresholds: parsedJson.coverage_thresholds,
        validation_thresholds: parsedJson.validation_thresholds,
      };

      const mission = await missionsApi.create(payload);
      onSuccess?.(mission);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create mission";
      setSubmitError(message);
    }
  };

  const onSubmitDraft = handleSubmit((values) => handleFormSubmit(values, "draft"));
  const onSubmitQueued = handleSubmit((values) => handleFormSubmit(values, "queued"));

  return (
    <form className="space-y-6">
      {/* Basic Information */}
      <section className={`${SECTION_CLASS} space-y-4`}>
        <header>
          <p className="text-xs uppercase tracking-widest text-gray-500 dark:text-gray-400">
            Required
          </p>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Mission Details
          </h2>
        </header>

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="form-label">
              Mission ID <span className="text-red-500">*</span>
            </label>
            <input
              {...register("mission_id")}
              placeholder="e.g., M-2024-001"
              className="form-input"
            />
            {errors.mission_id && (
              <p className="form-error">{errors.mission_id.message}</p>
            )}
          </div>

          <div>
            <label className="form-label">
              Title <span className="text-red-500">*</span>
            </label>
            <input
              {...register("title")}
              placeholder="Mission title"
              className="form-input"
            />
            {errors.title && <p className="form-error">{errors.title.message}</p>}
          </div>
        </div>

        <div>
          <label className="form-label">
            Objective <span className="text-red-500">*</span>
          </label>
          <textarea
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
          <p className="text-xs uppercase tracking-widest text-gray-500 dark:text-gray-400">
            Configuration
          </p>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Project & Settings
          </h2>
        </header>

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="form-label">
              Project <span className="text-red-500">*</span>
            </label>
            <select {...register("project_id")} className="form-input">
              <option value="">Select a project</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            {!isProjectSelected && (
              <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                Required — missions must belong to a project
              </p>
            )}
            {errors.project_id && (
              <p className="form-error">{errors.project_id.message}</p>
            )}
          </div>

          <div>
            <label className="form-label">Research Depth</label>
            <select {...register("research_depth")} className="form-input">
              <option value="baseline">Baseline - Standard (8-12 min, 50-60 sources)</option>
              <option value="deep">Deep - Higher Rigor (20-25 min, 30-40 sources)</option>
              <option value="alpha">Alpha - Maximum Rigor (1+ hour, ~20 sources)</option>
            </select>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Controls research thoroughness and source depth
            </p>
          </div>
        </div>

        <div>
          <label className="form-label">Priority</label>
          <select {...register("priority")} className="form-input">
            <option value="low">Low</option>
            <option value="normal">Normal</option>
            <option value="high">High</option>
          </select>
        </div>
      </section>

      {/* Research Contract — authoring fields consumed by DeepSearch */}
      <section className={`${SECTION_CLASS} space-y-4`}>
        <header>
          <p className="text-xs uppercase tracking-widest text-gray-500 dark:text-gray-400">
            Authoring Contract
          </p>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Research Contract
          </h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Optional fields the DeepSearch contract compiler reads when shaping
            retrieval and synthesis. Skip any that don't apply.
          </p>
        </header>

        <div>
          <label className="form-label">Background</label>
          <textarea
            {...register("background")}
            placeholder="Free-form prose orienting the research (e.g., what prior work is this building on?)"
            className="form-input min-h-[80px]"
          />
        </div>

        <div>
          <label className="form-label">Focus</label>
          <textarea
            {...register("focus")}
            placeholder="Narrow framing for the research question"
            className="form-input min-h-[60px]"
          />
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
              onChange={(items) => field.onChange(items.map((title) => ({ title })))}
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
              minItems={0}
            />
          )}
        />

        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <label className="form-label">Deliverable format</label>
            <input
              {...register("deliverable_format")}
              placeholder="e.g. markdown report, comparison table"
              className="form-input"
            />
          </div>
          <div>
            <label className="form-label">Min loops</label>
            <input
              type="number"
              min={1}
              max={50}
              {...register("min_loops", { valueAsNumber: true })}
              className="form-input"
            />
            {errors.min_loops && (
              <p className="form-error">{errors.min_loops.message}</p>
            )}
          </div>
          <div>
            <label className="form-label">Max loops</label>
            <input
              type="number"
              min={1}
              max={50}
              {...register("max_loops", { valueAsNumber: true })}
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
            <label className="form-label">{JSON_FIELD_LABELS[key]}</label>
            <textarea
              value={jsonFields[key]}
              onChange={(e) => {
                setJsonFields((prev) => ({ ...prev, [key]: e.target.value }));
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
          <p className="text-xs uppercase tracking-widest text-gray-500 dark:text-gray-400">
            Optional
          </p>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
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
              minItems={0}
            />
          )}
        />
      </section>

      {/* Error Display */}
      {submitError && (
        <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <p className="text-sm text-red-600 dark:text-red-400">{submitError}</p>
        </div>
      )}

      {/* Actions */}
      <section className={`${SECTION_CLASS}`}>
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-between">
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              Cancel
            </button>
          )}

          <div className="flex gap-3 sm:ml-auto">
            <button
              type="button"
              onClick={isProjectSelected ? onSubmitDraft : handleDisabledSubmitClick}
              disabled={isSubmitting}
              className={`px-4 py-2.5 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 ${
                isProjectSelected
                  ? "text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600"
                  : "text-gray-400 bg-gray-200 dark:bg-gray-700 cursor-not-allowed"
              }`}
              title={isProjectSelected ? undefined : "Select a project to save"}
            >
              {isSubmitting ? "Saving..." : "Save as Draft"}
            </button>

            <div className="relative">
              <button
                ref={submitButtonRef}
                type="button"
                onClick={isProjectSelected ? onSubmitQueued : handleDisabledSubmitClick}
                disabled={isSubmitting}
                className={`px-4 py-2.5 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 ${
                  isProjectSelected
                    ? "text-white bg-blue-600 hover:bg-blue-700"
                    : "text-gray-400 bg-gray-300 dark:bg-gray-600 cursor-not-allowed"
                }`}
                title={isProjectSelected ? undefined : "Select a project to submit to DeepSearch"}
              >
                {isSubmitting ? "Submitting..." : "Submit to DeepSearch"}
              </button>
              {showProjectRequiredTooltip && !isProjectSelected && (
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg whitespace-nowrap shadow-lg z-10">
                  Select a project to submit to DeepSearch
                  <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900 dark:border-t-gray-700" />
                </div>
              )}
            </div>
          </div>
        </div>
      </section>
    </form>
  );
}
