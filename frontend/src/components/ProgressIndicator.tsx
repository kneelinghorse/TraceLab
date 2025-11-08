type ProgressIndicatorProps = {
  value?: number | null;
  label?: string;
};

export function ProgressIndicator({ value = 0, label = "Completion" }: ProgressIndicatorProps) {
  const normalized = Math.min(100, Math.max(0, value ?? 0));
  const radius = 48;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (normalized / 100) * circumference;

  return (
    <div className="glass-card p-6 flex flex-col items-center justify-center w-full">
      <div className="text-sm uppercase tracking-[0.2em] text-slate-300 mb-3">{label}</div>
      <div className="relative flex items-center justify-center">
        <svg className="w-32 h-32 rotate-[-90deg]" viewBox="0 0 120 120">
          <circle cx="60" cy="60" r={radius} stroke="rgba(255,255,255,0.08)" strokeWidth="10" fill="transparent" />
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
              <stop offset="0%" stopColor="hsl(var(--accent))" />
              <stop offset="100%" stopColor="hsl(var(--accent-strong))" />
            </linearGradient>
          </defs>
        </svg>
        <div className="absolute text-4xl font-semibold text-white">{normalized}%</div>
      </div>
      <p className="text-sm text-slate-300 text-center mt-3">
        Tracking required Mission Protocol fields and quality checkpoints.
      </p>
    </div>
  );
}
