import { z } from "zod";

/**
 * Validation schema for creating a new API mission (B16.1+ schema).
 *
 * Includes mission-authoring fields promoted to root in Sprint 40 T40.1/T40.2:
 * background, focus, references, required_entities, excluded_entities,
 * expected_output_schema, coverage_thresholds, validation_thresholds,
 * deliverable_format, max_loops, min_loops, constraints. These are consumed
 * by DeepSearch's contract compiler.
 */
const missionReferenceSchema = z.object({
  title: z.string().min(1),
}).passthrough();

export const apiMissionFormSchema = z.object({
  // Required fields
  mission_id: z
    .string()
    .min(2, "Mission ID is required (min 2 characters)")
    .max(50, "Mission ID too long (max 50 characters)")
    .regex(/^[A-Za-z0-9._-]+$/, "Mission ID can only contain letters, numbers, dots, dashes, and underscores"),
  title: z
    .string()
    .min(3, "Title is required (min 3 characters)")
    .max(255, "Title too long (max 255 characters)"),
  objective: z
    .string()
    .min(10, "Objective should describe the mission goal (min 10 characters)"),
  success_criteria: z
    .array(z.string().min(1, "Criterion cannot be empty"))
    .min(1, "At least one success criterion is required"),

  // Optional fields
  project_id: z.string().optional(),
  context: z.record(z.string(), z.unknown()).optional(),
  deliverables: z.array(z.string()).optional(),
  research_phases: z.record(z.string(), z.unknown()).optional(),
  tags: z.array(z.string()).optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
  status: z.enum(["draft", "queued"]).optional(),
  priority: z.enum(["low", "normal", "high"]).optional(),
  research_depth: z.enum(["baseline", "deep", "alpha"]).optional(),

  // Authoring fields (T40.2) — all optional.
  background: z.string().optional(),
  focus: z.string().optional(),
  references: z.array(missionReferenceSchema).optional(),
  required_entities: z.array(z.string()).optional(),
  excluded_entities: z.array(z.string()).optional(),
  expected_output_schema: z.record(z.string(), z.unknown()).optional(),
  coverage_thresholds: z.record(z.string(), z.unknown()).optional(),
  validation_thresholds: z.record(z.string(), z.unknown()).optional(),
  deliverable_format: z.string().optional(),
  max_loops: z.number().int().min(1).max(50).optional(),
  min_loops: z.number().int().min(1).max(50).optional(),
  constraints: z.array(z.string()).optional(),
});

export type ApiMissionFormValues = z.infer<typeof apiMissionFormSchema>;

/**
 * Default values for a new mission form.
 */
export const defaultApiMissionFormValues: ApiMissionFormValues = {
  mission_id: "",
  title: "",
  objective: "",
  success_criteria: [""],
  project_id: "",
  deliverables: [],
  tags: [],
  metadata: {},
  status: "draft",
  priority: "normal",
  research_depth: "baseline",
  // Authoring fields default to undefined / empty so the form starts clean.
  background: "",
  focus: "",
  references: [],
  required_entities: [],
  excluded_entities: [],
  deliverable_format: "",
  constraints: [],
};
