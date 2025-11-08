import { z } from "zod";

export const missionFormSchema = z.object({
  projectId: z.string().uuid("Project ID must be a valid UUID"),
  missionId: z.string().min(2, "Mission ID is required"),
  title: z.string().min(3, "Title is required"),
  summary: z.string().min(10, "Summary should describe the mission intent"),
  owner: z.string().optional(),
  status: z.enum(["draft", "in_progress", "review", "complete"]),
  topic: z.string().min(3, "Topic required"),
  objective: z.string().min(3, "Objective required"),
  scope: z.string().min(3, "Scope required"),
  methodology: z.string().optional(),
  successMetrics: z.string().min(1, "List at least one success metric"),
  risks: z.string().min(1, "List at least one risk/assumption"),
  keyQuestions: z
    .array(
      z.object({
        question: z.string().min(3, "Question required"),
        status: z.enum(["open", "researching", "answered"]),
        answer: z.string().optional(),
        owner: z.string().optional(),
      }),
    )
    .min(1, "Add at least one key question"),
  keyInsights: z.string().min(1, "Provide at least one key insight"),
  surprisingFindings: z.string().optional().default(""),
  contradictions: z.string().optional().default(""),
  resolutions: z.string().optional().default(""),
  recommendations: z.string().min(1, "Add at least one recommendation"),
  nextSteps: z.string().min(1, "Add at least one next step"),
  evidence: z
    .array(
      z.object({
        evidence_id: z.string().min(1, "Evidence ID required"),
        source: z.string().min(1, "Evidence source required"),
        summary: z.string().min(8, "Evidence summary should provide context"),
        chunk_id: z.string().optional(),
        insight_id: z.string().optional(),
        source_type: z.string().optional(),
      }),
    )
    .min(1, "Provide at least one supporting chunk"),
  tags: z.string().optional().default(""),
});

export type MissionFormValues = z.input<typeof missionFormSchema>;
