import { z } from "zod";

/**
 * Validation schema for creating a new API mission (B16.1+ schema)
 * Matches ApiMissionCreate type requirements
 */
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

  // Optional fields with explicit types (no defaults in schema for RHF compatibility)
  project_id: z.string().optional(),
  context: z.object({
    background: z.string().optional(),
    constraints: z.array(z.string()).optional(),
  }).optional(),
  deliverables: z.array(z.string()).optional(),
  research_phases: z.record(z.string(), z.unknown()).optional(),
  tags: z.array(z.string()).optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
  status: z.enum(["draft", "queued"]).optional(),
  priority: z.enum(["low", "normal", "high"]).optional(),
  max_loops: z.number().min(1).max(10).optional(),
  research_depth: z.enum(["baseline", "deep", "alpha"]).optional(),
});

export type ApiMissionFormValues = z.infer<typeof apiMissionFormSchema>;

/**
 * Default values for a new mission form
 */
export const defaultApiMissionFormValues: ApiMissionFormValues = {
  mission_id: "",
  title: "",
  objective: "",
  success_criteria: [""],
  project_id: "",
  context: {
    background: "",
    constraints: [],
  },
  deliverables: [],
  tags: [],
  metadata: {},
  status: "draft",
  priority: "normal",
  max_loops: 3,
  research_depth: "baseline",
};
