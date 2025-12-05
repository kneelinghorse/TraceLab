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
  default: "bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700",
  blue: "bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800",
  green: "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800",
  yellow: "bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800",
  red: "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800",
  purple: "bg-purple-50 dark:bg-purple-900/20 border-purple-200 dark:border-purple-800",
};

const VALUE_COLORS = {
  default: "text-gray-900 dark:text-white",
  blue: "text-blue-900 dark:text-blue-100",
  green: "text-green-900 dark:text-green-100",
  yellow: "text-yellow-900 dark:text-yellow-100",
  red: "text-red-900 dark:text-red-100",
  purple: "text-purple-900 dark:text-purple-100",
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
      <div className={`${sizeClasses.label} font-medium text-gray-500 dark:text-gray-400 mb-1`}>
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
                ? "text-green-600 dark:text-green-400"
                : trend.direction === "down"
                ? "text-red-600 dark:text-red-400"
                : "text-gray-500 dark:text-gray-400"
            }`}
          >
            {trend.direction === "up" ? "↑" : trend.direction === "down" ? "↓" : "→"}
            {Math.abs(trend.value)}%
          </span>
        )}
      </div>
      {sublabel && (
        <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
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
