import type { FieldErrors, UseFormRegister, UseFieldArrayAppend, UseFieldArrayRemove } from "react-hook-form";

import type { MissionFormValues } from "@/lib/schemas/missionForm";

type EvidenceLinkingProps = {
  fields: { id: string }[];
  register: UseFormRegister<MissionFormValues>;
  errors: FieldErrors<MissionFormValues>;
  append: UseFieldArrayAppend<MissionFormValues, "evidence">;
  remove: UseFieldArrayRemove;
};

const EMPTY_EVIDENCE = {
  evidence_id: "",
  source: "",
  summary: "",
  chunk_id: "",
  insight_id: "",
  source_type: "",
};

export function EvidenceLinking({ fields, register, errors, append, remove }: EvidenceLinkingProps) {
  return (
    <div className="space-y-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Evidence</p>
          <h3 className="text-2xl font-semibold text-slate-900">Evidence Linking</h3>
        </div>
        <button
          type="button"
          onClick={() => append(EMPTY_EVIDENCE)}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
        >
          Add Evidence
        </button>
      </div>
      <p className="text-sm text-slate-600">
        Link insights back to supporting document chunks to satisfy the <strong>traceability</strong> gate.
      </p>
      <div className="space-y-4">
        {fields.map((field, index) => (
          <div key={field.id ?? index} className="space-y-3 rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label className="form-label">Evidence ID</label>
                <input {...register(`evidence.${index}.evidence_id` as const)} className="form-input" placeholder="EV-001" />
                {errors.evidence?.[index]?.evidence_id && (
                  <p className="mt-1 text-xs text-rose-600">{errors.evidence[index]?.evidence_id?.message as string}</p>
                )}
              </div>
              <div>
                <label className="form-label">Source</label>
                <input {...register(`evidence.${index}.source` as const)} className="form-input" placeholder="Interview transcript" />
              </div>
            </div>
            <div>
              <label className="form-label">Summary</label>
              <textarea
                {...register(`evidence.${index}.summary` as const)}
                className="form-input min-h-[90px]"
                placeholder="Key quote or finding..."
              />
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <div>
                <label className="form-label">Chunk ID</label>
                <input {...register(`evidence.${index}.chunk_id` as const)} className="form-input" placeholder="chunk_8f2c" />
              </div>
              <div>
                <label className="form-label">Insight ID</label>
                <input {...register(`evidence.${index}.insight_id` as const)} className="form-input" placeholder="INS-123" />
              </div>
              <div>
                <label className="form-label">Source Type</label>
                <input
                  {...register(`evidence.${index}.source_type` as const)}
                  className="form-input"
                  placeholder="interview, log, survey"
                />
              </div>
            </div>
            <div className="flex justify-end">
              <button type="button" onClick={() => remove(index)} className="text-sm font-medium text-rose-600 hover:text-rose-700">
                Remove evidence
              </button>
            </div>
          </div>
        ))}
        {fields.length === 0 && (
          <div className="rounded-2xl border border-dashed border-slate-300 p-6 text-center text-slate-600">
            Attach at least one evidence record to satisfy traceability.
          </div>
        )}
      </div>
    </div>
  );
}
