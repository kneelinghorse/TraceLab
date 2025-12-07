import { useState } from "react";

interface ResearchTask {
  name: string;
  status?: "pending" | "in_progress" | "completed";
  description?: string;
}

interface ResearchPhase {
  name: string;
  description?: string;
  tasks?: ResearchTask[];
}

interface ResearchPhasesProps {
  phases: Record<string, unknown>;
}

function ChevronIcon({ isOpen }: { isOpen: boolean }) {
  return (
    <svg
      className={`w-5 h-5 transition-transform ${isOpen ? "rotate-90" : ""}`}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
    </svg>
  );
}

function TaskStatusIcon({ status }: { status?: string }) {
  if (status === "completed") {
    return (
      <span className="w-4 h-4 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
        <svg className="w-2.5 h-2.5 text-emerald-500" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
            clipRule="evenodd"
          />
        </svg>
      </span>
    );
  }
  if (status === "in_progress") {
    return <span className="w-4 h-4 rounded-full bg-blue-400 animate-pulse" />;
  }
  return <span className="w-4 h-4 rounded-full bg-gray-200 dark:bg-gray-700" />;
}

function PhaseSection({ phase, index }: { phase: ResearchPhase; index: number }) {
  const [isOpen, setIsOpen] = useState(index === 0);
  const tasks = phase.tasks ?? [];

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-750 transition-colors text-left"
      >
        <div className="flex items-center gap-3">
          <span className="w-6 h-6 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 flex items-center justify-center text-xs font-bold">
            {index + 1}
          </span>
          <span className="font-medium text-gray-900 dark:text-white">{phase.name}</span>
          {tasks.length > 0 && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              ({tasks.length} task{tasks.length !== 1 ? "s" : ""})
            </span>
          )}
        </div>
        <ChevronIcon isOpen={isOpen} />
      </button>

      {isOpen && (
        <div className="p-4 bg-white dark:bg-gray-900">
          {phase.description && (
            <p className="text-gray-600 dark:text-gray-300 text-sm mb-4">{phase.description}</p>
          )}

          {tasks.length > 0 ? (
            <ul className="space-y-2">
              {tasks.map((task, taskIndex) => (
                <li key={taskIndex} className="flex items-start gap-3">
                  <TaskStatusIcon status={task.status} />
                  <div className="flex-1 min-w-0">
                    <p className="text-gray-900 dark:text-white text-sm">{task.name}</p>
                    {task.description && (
                      <p className="text-gray-500 dark:text-gray-400 text-xs mt-0.5">{task.description}</p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-gray-500 dark:text-gray-400 text-sm">No tasks defined for this phase.</p>
          )}
        </div>
      )}
    </div>
  );
}

function parsePhases(phases: Record<string, unknown>): ResearchPhase[] {
  const result: ResearchPhase[] = [];

  for (const [key, value] of Object.entries(phases)) {
    if (typeof value === "object" && value !== null) {
      const phaseData = value as Record<string, unknown>;
      result.push({
        name: (phaseData.name as string) ?? key,
        description: phaseData.description as string | undefined,
        tasks: Array.isArray(phaseData.tasks)
          ? phaseData.tasks.map((t: unknown) => {
              if (typeof t === "string") {
                return { name: t };
              }
              if (typeof t === "object" && t !== null) {
                const taskObj = t as Record<string, unknown>;
                return {
                  name: (taskObj.name as string) ?? String(t),
                  status: taskObj.status as ResearchTask["status"],
                  description: taskObj.description as string | undefined,
                };
              }
              return { name: String(t) };
            })
          : undefined,
      });
    } else if (typeof value === "string") {
      result.push({ name: key, description: value });
    }
  }

  return result;
}

export function ResearchPhases({ phases }: ResearchPhasesProps) {
  const parsedPhases = parsePhases(phases);

  if (parsedPhases.length === 0) {
    return (
      <div className="text-gray-500 dark:text-gray-400 text-sm py-2">
        No research phases defined.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {parsedPhases.map((phase, index) => (
        <PhaseSection key={index} phase={phase} index={index} />
      ))}
    </div>
  );
}
