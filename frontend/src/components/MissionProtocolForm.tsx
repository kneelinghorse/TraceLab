import { useEffect, useMemo, useState } from "react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { createMission, updateMission } from "@/lib/api/missions";
import type { Mission } from "@/types/mission";
import { EvidenceLinking } from "@/components/EvidenceLinking";
import { missionFormSchema, type MissionFormValues } from "@/lib/schemas/missionForm";

const SECTION_CLASS = "rounded-3xl border border-slate-200 bg-white p-6 shadow-sm";

type MissionProtocolFormProps = {
  mission?: Mission;
  onCompleted?: (mission: Mission) => void;
};

const DEFAULT_QUESTION = { question: "", status: "open" as const, answer: "", owner: "" };
const DEFAULT_EVIDENCE = {
  evidence_id: "",
  source: "",
  summary: "",
  chunk_id: "",
  insight_id: "",
  source_type: "",
};

const DEFAULT_PROJECT_ID = process.env.NEXT_PUBLIC_DEFAULT_PROJECT_ID ?? "";

const MISSION_TEMPLATES: Array<{
  id: string;
  name: string;
  description: string;
  values: Partial<MissionFormValues>;
}> = [
  {
    id: "competitive-analysis",
    name: "Competitive Analysis",
    description: "Evaluate rival offerings, capture differentiators, and record risks.",
    values: {
      title: "Competitive analysis mission",
      summary: "Assess competitor positioning, feature gaps, and buyer blockers.",
      topic: "Competitive intelligence",
      objective: "Document differentiators and opportunities",
      scope: "Mission Protocol + RAG search",
      successMetrics: "3 insights on differentiators\nActionable blockers",
      risks: "Incomplete data\nBiased samples",
      keyQuestions: [
        { question: "Where does the competitor outperform us?", status: "open", answer: "", owner: "" },
        { question: "What risks block adoption?", status: "open", answer: "", owner: "" },
      ],
      methodology: "Document review + SME interviews",
      tags: "competitive,analysis",
    },
  },
  {
    id: "technical-dive",
    name: "Technical Deep Dive",
    description: "Capture architecture, trade-offs, and implementation recommendations.",
    values: {
      title: "Technical deep dive",
      summary: "Research architecture choices, integration risks, and performance levers.",
      topic: "Technical evaluation",
      objective: "Outline architecture + integration approach",
      scope: "API layer + Mission Protocol UI",
      methodology: "Code review + RAG references",
      successMetrics: "Architecture diagram\nList of integration blockers",
      keyQuestions: [
        { question: "Which services must we touch?", status: "open", answer: "", owner: "" },
      ],
      tags: "tech,evaluation",
    },
  },
];

const convertArrayToMultiline = (items?: string[] | null) => (items && items.length ? items.join("\n") : "");

const normalize = (value?: string | null) => {
  if (!value) {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed.length ? trimmed : undefined;
};

const convertMissionToFormValues = (mission?: Mission): MissionFormValues => {
  if (!mission) {
    return {
      projectId: DEFAULT_PROJECT_ID,
      missionId: "",
      title: "",
      summary: "",
      owner: "",
      status: "draft",
      topic: "",
      objective: "",
      scope: "",
      methodology: "",
      successMetrics: "",
      risks: "",
      keyQuestions: [DEFAULT_QUESTION],
      keyInsights: "",
      surprisingFindings: "",
      contradictions: "",
      resolutions: "",
      recommendations: "",
      nextSteps: "",
      evidence: [DEFAULT_EVIDENCE],
      tags: "",
    };
  }

  const protocol = mission.mission_data;
  return {
    projectId: mission.project_id ?? DEFAULT_PROJECT_ID,
    missionId: protocol.mission_id,
    title: protocol.title ?? "",
    summary: protocol.summary ?? "",
    owner: protocol.owner ?? "",
    status: protocol.status ?? "draft",
    topic: protocol.research_statement?.topic ?? "",
    objective: protocol.research_statement?.objective ?? "",
    scope: protocol.research_statement?.scope ?? "",
    methodology: protocol.research_statement?.methodology ?? "",
    successMetrics: convertArrayToMultiline(protocol.research_statement?.success_metrics),
    risks: convertArrayToMultiline(protocol.research_statement?.risks),
    keyQuestions:
      protocol.key_questions.length > 0
        ? protocol.key_questions.map((question) => ({
            question: question.question,
            status: question.status,
            answer: question.answer ?? "",
            owner: question.owner ?? "",
          }))
        : [DEFAULT_QUESTION],
    keyInsights: convertArrayToMultiline(protocol.synthesis?.key_insights),
    surprisingFindings: convertArrayToMultiline(protocol.synthesis?.surprising_findings),
    contradictions: convertArrayToMultiline(protocol.synthesis?.contradictory_information),
    resolutions: convertArrayToMultiline(protocol.synthesis?.contradiction_resolutions),
    recommendations: convertArrayToMultiline(protocol.synthesis?.recommendations),
    nextSteps: convertArrayToMultiline(protocol.synthesis?.next_steps),
    evidence:
      protocol.evidence.length > 0
        ? protocol.evidence.map((item) => ({
            evidence_id: item.evidence_id,
            source: item.source,
            summary: item.summary,
            chunk_id: item.chunk_id ?? "",
            insight_id: item.insight_id ?? "",
            source_type: item.source_type ?? "",
          }))
        : [DEFAULT_EVIDENCE],
    tags: protocol.tags.join(", "),
  };
};

const multilineToArray = (value?: string) =>
  (value ?? "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

export function MissionProtocolForm({ mission, onCompleted }: MissionProtocolFormProps) {
  const defaultValues = useMemo(() => convertMissionToFormValues(mission), [mission]);
  const {
    control,
    register,
    handleSubmit,
    getValues,
    formState: { errors, isSubmitting },
    reset,
  } = useForm<MissionFormValues>({
    defaultValues,
    resolver: zodResolver(missionFormSchema),
    mode: "onBlur",
  });

  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");

  useEffect(() => {
    reset(defaultValues);
  }, [defaultValues, reset]);

  const { fields: questionFields, append: appendQuestion, remove: removeQuestion } = useFieldArray({
    control,
    name: "keyQuestions",
  });

  const { fields: evidenceFields, append: appendEvidence, remove: removeEvidence } = useFieldArray({
    control,
    name: "evidence",
  });

  const keyInsightsValue = useWatch({ control, name: "keyInsights" });
  const selectedTemplate = MISSION_TEMPLATES.find((item) => item.id === selectedTemplateId);

  const handleTemplateApply = () => {
    const template = MISSION_TEMPLATES.find((item) => item.id === selectedTemplateId);
    if (!template) {
      return;
    }
    const current = getValues();
    const templateQuestions = template.values.keyQuestions
      ? template.values.keyQuestions.map((question) => ({ ...question }))
      : current.keyQuestions;

    reset({
      ...current,
      ...template.values,
      keyQuestions: templateQuestions,
    });
  };

  const onSubmit = handleSubmit(async (values) => {
    const missionPayload = {
      ...mission?.mission_data,
      mission_id: values.missionId,
      version: mission?.mission_data.version ?? "1.0.0",
      title: values.title.trim(),
      summary: values.summary.trim(),
      owner: normalize(values.owner),
      status: values.status,
      project_id: values.projectId,
      research_statement: {
        topic: values.topic.trim(),
        objective: values.objective.trim(),
        scope: values.scope.trim(),
        methodology: normalize(values.methodology),
        success_metrics: multilineToArray(values.successMetrics),
        risks: multilineToArray(values.risks),
        audience: mission?.mission_data.research_statement?.audience,
      },
      key_questions: values.keyQuestions.map((entry: MissionFormValues["keyQuestions"][number]) => ({
        question: entry.question,
        status: entry.status,
        answer: normalize(entry.answer),
        owner: normalize(entry.owner),
      })),
      synthesis: {
        key_insights: multilineToArray(values.keyInsights),
        surprising_findings: multilineToArray(values.surprisingFindings),
        contradictory_information: multilineToArray(values.contradictions),
        contradiction_resolutions: multilineToArray(values.resolutions),
        recommendations: multilineToArray(values.recommendations),
        next_steps: multilineToArray(values.nextSteps),
      },
      evidence: values.evidence.map((entry: MissionFormValues["evidence"][number]) => ({
        ...entry,
        chunk_id: normalize(entry.chunk_id),
        insight_id: normalize(entry.insight_id),
        source_type: normalize(entry.source_type),
        relevance_score: mission?.mission_data.evidence.find((ev) => ev.evidence_id === entry.evidence_id)?.relevance_score,
        tags: mission?.mission_data.evidence.find((ev) => ev.evidence_id === entry.evidence_id)?.tags ?? [],
      })),
      quality_checkpoints: mission?.mission_data.quality_checkpoints ?? [],
      tags: (values.tags ?? "")
        .split(",")
        .map((tag: string) => tag.trim())
        .filter(Boolean),
    };

    const payload = {
      project_id: values.projectId,
      mission_data: missionPayload,
      status: values.status,
    };

    const nextMission = mission ? await updateMission(mission.id, payload) : await createMission(payload);
    onCompleted?.(nextMission);
  });

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      <section className={`${SECTION_CLASS} space-y-4`}>
        <header>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Mission Metadata</p>
          <h2 className="text-2xl font-semibold text-slate-900">Mission Protocol Draft</h2>
        </header>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="form-label">Project ID</label>
            <input {...register("projectId")} placeholder="UUID" className="form-input" />
            {errors.projectId && <p className="form-error">{errors.projectId.message}</p>}
          </div>
          <div>
            <label className="form-label">Mission ID</label>
            <input {...register("missionId")} placeholder="B3.4" className="form-input" />
            {errors.missionId && <p className="form-error">{errors.missionId.message}</p>}
          </div>
          <div>
            <label className="form-label">Title</label>
            <input {...register("title")} placeholder="UI Integration" className="form-input" />
          </div>
          <div>
            <label className="form-label">Owner</label>
            <input {...register("owner")} placeholder="Research lead" className="form-input" />
          </div>
          <div>
            <label className="form-label">Status</label>
            <select {...register("status")} className="form-input">
              <option value="draft">Draft</option>
              <option value="in_progress">In Progress</option>
              <option value="review">Review</option>
              <option value="complete">Complete</option>
            </select>
          </div>
          <div>
            <label className="form-label">Summary</label>
            <textarea {...register("summary")} className="form-input min-h-[90px]" placeholder="Mission synopsis" />
            {errors.summary && <p className="form-error">{errors.summary.message}</p>}
          </div>
        </div>
        <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4">
          <p className="text-sm font-semibold text-slate-800">Mission templates</p>
          <div className="mt-2 flex flex-col gap-3 md:flex-row">
            <select
              value={selectedTemplateId}
              onChange={(event) => setSelectedTemplateId(event.target.value)}
              className="form-input md:flex-1"
            >
              <option value="">Choose template…</option>
              {MISSION_TEMPLATES.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={handleTemplateApply}
              disabled={!selectedTemplateId}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            >
              Apply template
            </button>
          </div>
          {selectedTemplate && <p className="mt-2 text-xs text-slate-500">{selectedTemplate.description}</p>}
        </div>
      </section>

      <section className={`${SECTION_CLASS} space-y-4`}>
        <header>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Research Statement</p>
          <h2 className="text-2xl font-semibold text-slate-900">Anchor the Mission</h2>
        </header>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="form-label">Topic</label>
            <input {...register("topic")} className="form-input" />
            {errors.topic && <p className="form-error">{errors.topic.message}</p>}
          </div>
          <div>
            <label className="form-label">Objective</label>
            <input {...register("objective")} className="form-input" />
            {errors.objective && <p className="form-error">{errors.objective.message}</p>}
          </div>
          <div>
            <label className="form-label">Scope</label>
            <input {...register("scope")} className="form-input" />
            {errors.scope && <p className="form-error">{errors.scope.message}</p>}
          </div>
          <div>
            <label className="form-label">Methodology</label>
            <input {...register("methodology")} className="form-input" placeholder="Primary research method" />
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="form-label">Success Metrics (one per line)</label>
            <textarea {...register("successMetrics")} className="form-input min-h-[120px]" />
            {errors.successMetrics && <p className="form-error">{errors.successMetrics.message}</p>}
          </div>
          <div>
            <label className="form-label">Risks & Assumptions (one per line)</label>
            <textarea {...register("risks")} className="form-input min-h-[120px]" />
            {errors.risks && <p className="form-error">{errors.risks.message}</p>}
          </div>
        </div>
      </section>

      <section className={`${SECTION_CLASS} space-y-4`}>
        <header className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Key Questions</p>
            <h2 className="text-2xl font-semibold text-slate-900">Decision Frame</h2>
          </div>
          <button
            type="button"
            onClick={() => appendQuestion(DEFAULT_QUESTION)}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800"
          >
            Add Key Question
          </button>
        </header>
        <div className="space-y-4">
          {questionFields.map((field, index) => (
            <div key={field.id} className="grid gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 md:grid-cols-4">
              <div className="md:col-span-2">
                <label className="form-label">Question</label>
                <input {...register(`keyQuestions.${index}.question` as const)} className="form-input" />
                {errors.keyQuestions?.[index]?.question && (
                  <p className="form-error">{errors.keyQuestions?.[index]?.question?.message}</p>
                )}
              </div>
              <div>
                <label className="form-label">Status</label>
                <select {...register(`keyQuestions.${index}.status` as const)} className="form-input">
                  <option value="open">Open</option>
                  <option value="researching">Researching</option>
                  <option value="answered">Answered</option>
                </select>
              </div>
              <div>
                <label className="form-label">Owner</label>
                <input {...register(`keyQuestions.${index}.owner` as const)} className="form-input" />
              </div>
              <div className="md:col-span-3">
                <label className="form-label">Answer / Notes</label>
                <textarea {...register(`keyQuestions.${index}.answer` as const)} className="form-input min-h-[70px]" />
              </div>
              <div className="flex items-center justify-end">
                <button type="button" onClick={() => removeQuestion(index)} className="text-sm font-medium text-rose-600 hover:text-rose-700">
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className={`${SECTION_CLASS} space-y-4`}>
        <header>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Synthesis</p>
          <h2 className="text-2xl font-semibold text-slate-900">Insights & Next Steps</h2>
        </header>
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <label className="form-label">Key Insights (Markdown supported)</label>
            <textarea {...register("keyInsights")} className="form-input min-h-[180px]" placeholder="* Insight with citation" />
            {errors.keyInsights && <p className="form-error">{errors.keyInsights.message}</p>}
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">Preview</p>
            <div className="markdown-preview mt-2 min-h-[140px]">
              {keyInsightsValue ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{keyInsightsValue}</ReactMarkdown>
              ) : (
                <p className="text-slate-500">Write insights on the left to render Markdown preview.</p>
              )}
            </div>
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="form-label">Recommendations</label>
            <textarea {...register("recommendations")} className="form-input min-h-[140px]" placeholder="One per line" />
            {errors.recommendations && <p className="form-error">{errors.recommendations.message}</p>}
          </div>
          <div>
            <label className="form-label">Next Steps</label>
            <textarea {...register("nextSteps")} className="form-input min-h-[140px]" placeholder="One per line" />
            {errors.nextSteps && <p className="form-error">{errors.nextSteps.message}</p>}
          </div>
          <div>
            <label className="form-label">Surprising Findings</label>
            <textarea
              {...register("surprisingFindings")}
              className="form-input min-h-[140px]"
              placeholder="Optional – one per line"
            />
          </div>
          <div>
            <label className="form-label">Contradictions</label>
            <textarea {...register("contradictions")} className="form-input min-h-[140px]" placeholder="One per line" />
          </div>
          <div>
            <label className="form-label">Resolutions</label>
            <textarea {...register("resolutions")} className="form-input min-h-[140px]" placeholder="One per line" />
          </div>
        </div>
      </section>

      <EvidenceLinking
        fields={evidenceFields}
        register={register}
        errors={errors}
        append={appendEvidence}
        remove={removeEvidence}
      />

      <section className={`${SECTION_CLASS} space-y-4`}>
        <div>
          <label className="form-label">Tags (comma separated)</label>
          <input {...register("tags")} placeholder="mission protocol, ui" className="form-input" />
        </div>
        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full py-3 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-500 text-white font-semibold shadow-lg shadow-sky-900/40 disabled:opacity-50"
        >
          {mission ? "Update Mission" : "Create Mission"}
        </button>
      </section>
    </form>
  );
}
