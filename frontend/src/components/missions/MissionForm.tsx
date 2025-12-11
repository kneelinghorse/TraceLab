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

/**
 * Form for creating a new DeepSearch mission.
 * Supports "Save as Draft" and "Submit Immediately" actions.
 */
export function MissionForm({ onSuccess, onCancel }: MissionFormProps) {
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showProjectRequiredTooltip, setShowProjectRequiredTooltip] = useState(false);
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

  const handleDisabledSubmitClick = () => {
    setShowProjectRequiredTooltip(true);
    setSubmitError("A project must be selected to submit to DeepSearch. Select a project above or save as draft.");
  };

  const handleFormSubmit = async (
    values: ApiMissionFormValues,
    submitStatus: "draft" | "queued"
  ) => {
    setSubmitError(null);

    try {
      const payload: ApiMissionCreate = {
        mission_id: values.mission_id,
        title: values.title,
        objective: values.objective,
        success_criteria: values.success_criteria.filter((c) => c.trim() !== ""),
        project_id: values.project_id || undefined,
        context: {
          background: values.context?.background || undefined,
          constraints: values.context?.constraints?.filter((c) => c.trim() !== "") || [],
        },
        deliverables: values.deliverables?.filter((d) => d.trim() !== "") || [],
        tags: values.tags?.filter((t) => t.trim() !== "") || [],
        metadata: {
          priority: values.priority,
          max_loops: values.max_loops,
          ...values.metadata,
        },
        research_depth: values.research_depth || "baseline",
        status: submitStatus,
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
              Project {!isProjectSelected && <span className="text-red-500">*</span>}
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
                Required for DeepSearch submission
              </p>
            )}
            {errors.project_id && (
              <p className="form-error">{errors.project_id.message}</p>
            )}
          </div>

          <div>
            <label className="form-label">Research Depth</label>
            <select {...register("research_depth")} className="form-input">
              <option value="baseline">Baseline - Quick (2-4 min)</option>
              <option value="deep">Deep - Thorough (5-10 min)</option>
              <option value="alpha">Alpha - Comprehensive (8-15 min)</option>
            </select>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Controls research thoroughness and source depth
            </p>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="form-label">Priority</label>
            <select {...register("priority")} className="form-input">
              <option value="low">Low</option>
              <option value="normal">Normal</option>
              <option value="high">High</option>
            </select>
          </div>

          <div>
            <label className="form-label">Max Loops</label>
            <input
              type="number"
              {...register("max_loops", { valueAsNumber: true })}
              min={1}
              max={10}
              className="form-input"
            />
            {errors.max_loops && (
              <p className="form-error">{errors.max_loops.message}</p>
            )}
          </div>
        </div>
      </section>

      {/* Context */}
      <section className={`${SECTION_CLASS} space-y-4`}>
        <header>
          <p className="text-xs uppercase tracking-widest text-gray-500 dark:text-gray-400">
            Optional
          </p>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Context
          </h2>
        </header>

        <div>
          <label className="form-label">Background</label>
          <textarea
            {...register("context.background")}
            placeholder="Provide additional context or background information..."
            className="form-input min-h-[80px]"
          />
        </div>

        <Controller
          control={control}
          name="context.constraints"
          render={({ field }) => (
            <DynamicListInput
              label="Constraints"
              items={field.value ?? []}
              onChange={field.onChange}
              placeholder="Add a constraint or limitation..."
              minItems={0}
            />
          )}
        />
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
              onClick={onSubmitDraft}
              disabled={isSubmitting}
              className="px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors disabled:opacity-50"
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
