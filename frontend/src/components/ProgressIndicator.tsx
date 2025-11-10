import type { Mission } from "@/types/mission";

type ProgressIndicatorProps = {
  value?: number | null;
  label?: string;
  mission?: Mission;
};

const REQUIRED_FIELDS = [
  { label: "Summary", isPresent: (mission?: Mission) => Boolean(mission?.mission_data.summary?.trim()) },
  { label: "Owner", isPresent: (mission?: Mission) => Boolean(mission?.mission_data.owner?.trim()) },
  { label: "Research statement", isPresent: (mission?: Mission) => Boolean(mission?.mission_data.research_statement?.topic?.trim()) },
  {
    label: "Key question",
    isPresent: (mission?: Mission) => Boolean(mission?.mission_data.key_questions?.length && mission.mission_data.key_questions[0]?.question?.trim()),
  },
  {
    label: "Evidence",
    isPresent: (mission?: Mission) => Boolean(mission?.mission_data.evidence?.length),
  },
];

export function ProgressIndicator({ value = 0, label = "Completion", mission }: ProgressIndicatorProps) {
  const normalized = Math.min(100, Math.max(0, value ?? 0));
  const radius = 48;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (normalized / 100) * circumference;
  const missingFields = REQUIRED_FIELDS.filter((rule) => !rule.isPresent(mission)).map((rule) => rule.label);

  return (
    <div className="w-full rounded-3xl border border-slate-200 bg-white p-6 text-slate-900 shadow-sm">
      <div className="text-sm font-semibold uppercase tracking-[0.3em] text-slate-500">{label}</div>
      <div className="relative mt-4 flex items-center justify-center">
        <svg className="h-32 w-32 text-slate-200" viewBox="0 0 120 120">
          <circle cx="60" cy="60" r={radius} stroke="currentColor" strokeWidth="10" fill="transparent" />
          <circle
            cx="60"
            cy="60"
            r={radius}
            stroke="url(#progress-gradient)"
            strokeWidth="10"
            fill="transparent"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
          />
          <defs>
            <linearGradient id="progress-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="hsl(199 89% 48%)" />
              <stop offset="100%" stopColor="hsl(210 96% 60%)" />
            </linearGradient>
          </defs>
        </svg>
        <div className="absolute text-4xl font-semibold text-slate-900">{normalized}%</div>
      </div>
      {missingFields.length === 0 ? (
        <p className="mt-3 text-sm text-emerald-700">All required fields are populated.</p>
      ) : (
        <div className="mt-3 text-sm text-slate-600">
          <p className="font-medium text-slate-900">Missing fields</p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {missingFields.map((field) => (
              <li key={field}>{field}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
