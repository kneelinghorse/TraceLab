/**
 * StatCard - Simple statistics display card for the console dashboard.
 */

interface StatCardProps {
  label: string;
  value: number | string;
  sublabel?: string;
  trend?: {
    value: number;
    direction: "up" | "down" | "neutral";
  };
  color?: "default" | "blue" | "green" | "yellow" | "red" | "purple";
  size?: "sm" | "md" | "lg";
}

const COLOR_CLASSES = {
  default: "bg-surface dark:bg-surface border-line dark:border-line",
  blue: "bg-info-surface dark:bg-info-surface border-info-line dark:border-info-line",
  green: "bg-success-surface dark:bg-success-surface border-success-line dark:border-success-line",
  yellow: "bg-warning-surface dark:bg-warning-surface border-warning-line dark:border-warning-line",
  red: "bg-danger-surface dark:bg-danger-surface border-danger-line dark:border-danger-line",
  purple: "bg-info-surface dark:bg-info-surface border-info-line dark:border-info-line",
};

const VALUE_COLORS = {
  default: "text-foreground dark:text-foreground",
  blue: "text-info dark:text-accent-text",
  green: "text-success dark:text-success",
  yellow: "text-warning dark:text-warning",
  red: "text-danger dark:text-danger",
  purple: "text-info dark:text-accent-text",
};

const SIZE_CLASSES = {
  sm: { container: "p-3", value: "text-xl", label: "text-xs" },
  md: { container: "p-4", value: "text-2xl", label: "text-sm" },
  lg: { container: "p-6", value: "text-4xl", label: "text-base" },
};

export function StatCard({
  label,
  value,
  sublabel,
  trend,
  color = "default",
  size = "md",
}: StatCardProps) {
  const sizeClasses = SIZE_CLASSES[size];

  return (
    <div
      className={`rounded-lg border ${COLOR_CLASSES[color]} ${sizeClasses.container}`}
    >
      <div className={`${sizeClasses.label} font-medium text-secondary dark:text-secondary mb-1`}>
        {label}
      </div>
      <div className="flex items-end gap-2">
        <span className={`${sizeClasses.value} font-bold ${VALUE_COLORS[color]}`}>
          {value}
        </span>
        {trend && (
          <span
            className={`text-sm ${
              trend.direction === "up"
                ? "text-success dark:text-success"
                : trend.direction === "down"
                ? "text-danger dark:text-danger"
                : "text-secondary dark:text-secondary"
            }`}
          >
            {trend.direction === "up" ? "↑" : trend.direction === "down" ? "↓" : "→"}
            {Math.abs(trend.value)}%
          </span>
        )}
      </div>
      {sublabel && (
        <div className="text-xs text-secondary dark:text-secondary mt-1">
          {sublabel}
        </div>
      )}
    </div>
  );
}

interface StatGridProps {
  children: React.ReactNode;
  columns?: 2 | 3 | 4 | 5;
}

export function StatGrid({ children, columns = 4 }: StatGridProps) {
  const colClasses = {
    2: "grid-cols-1 sm:grid-cols-2",
    3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
    4: "grid-cols-2 lg:grid-cols-4",
    5: "grid-cols-2 md:grid-cols-3 lg:grid-cols-5",
  };

  return <div className={`grid gap-4 ${colClasses[columns]}`}>{children}</div>;
}
