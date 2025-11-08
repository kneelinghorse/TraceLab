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
    <div className="glass-card p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Evidence</p>
          <h3 className="text-2xl font-semibold text-white">Evidence Linking</h3>
        </div>
        <button
          type="button"
          onClick={() => append(EMPTY_EVIDENCE)}
          className="px-4 py-2 rounded-lg bg-gradient-to-r from-sky-500 to-indigo-500 text-white text-sm font-semibold shadow-lg shadow-sky-900/40"
        >
          Add Evidence
        </button>
      </div>
      <p className="text-sm text-slate-300">
        Link insights back to their supporting document chunks to satisfy the <strong>traceability</strong> quality gate.
      </p>
      <div className="space-y-4">
        {fields.map((field, index) => (
          <div key={field.id ?? index} className="border border-white/10 rounded-2xl p-4 space-y-3 bg-black/20">
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label className="text-xs uppercase tracking-[0.3em] text-slate-400 block mb-1">Evidence ID</label>
                <input
                  {...register(`evidence.${index}.evidence_id` as const)}
                  className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2 focus:ring-2 focus:ring-sky-400/50 focus:outline-none"
                  placeholder="EV-001"
                />
                {errors.evidence?.[index]?.evidence_id && (
                  <p className="text-xs text-rose-300 mt-1">{errors.evidence[index]?.evidence_id?.message as string}</p>
                )}
              </div>
              <div>
                <label className="text-xs uppercase tracking-[0.3em] text-slate-400 block mb-1">Source</label>
                <input
                  {...register(`evidence.${index}.source` as const)}
                  className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2 focus:ring-2 focus:ring-sky-400/50 focus:outline-none"
                  placeholder="Interview transcript"
                />
              </div>
            </div>
            <div>
              <label className="text-xs uppercase tracking-[0.3em] text-slate-400 block mb-1">Summary</label>
              <textarea
                {...register(`evidence.${index}.summary` as const)}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2 focus:ring-2 focus:ring-sky-400/50 focus:outline-none min-h-[90px]"
                placeholder="Key quote or finding..."
              />
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <div>
                <label className="text-xs uppercase tracking-[0.3em] text-slate-400 block mb-1">Chunk ID</label>
                <input
                  {...register(`evidence.${index}.chunk_id` as const)}
                  className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2 focus:ring-2 focus:ring-sky-400/50 focus:outline-none"
                  placeholder="chunk_8f2c"
                />
              </div>
              <div>
                <label className="text-xs uppercase tracking-[0.3em] text-slate-400 block mb-1">Insight ID</label>
                <input
                  {...register(`evidence.${index}.insight_id` as const)}
                  className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2 focus:ring-2 focus:ring-sky-400/50 focus:outline-none"
                  placeholder="INS-123"
                />
              </div>
              <div>
                <label className="text-xs uppercase tracking-[0.3em] text-slate-400 block mb-1">Source Type</label>
                <input
                  {...register(`evidence.${index}.source_type` as const)}
                  className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2 focus:ring-2 focus:ring-sky-400/50 focus:outline-none"
                  placeholder="interview, log, survey"
                />
              </div>
            </div>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => remove(index)}
                className="text-sm text-rose-300 hover:text-rose-200"
              >
                Remove evidence
              </button>
            </div>
          </div>
        ))}
        {fields.length === 0 && (
          <div className="rounded-2xl border border-dashed border-white/20 p-6 text-center text-slate-300">
            Attach at least one evidence record to satisfy traceability.
          </div>
        )}
      </div>
    </div>
  );
}
