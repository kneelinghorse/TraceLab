import { useEffect, useState } from "react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";

import { AuthGate } from "@/components/AuthGate";
import { projectsApi } from "@/lib/api/projects";
import { calculateQueuePosition, useApiMissions } from "@/lib/hooks/useMissions";
import type { ApiMission, MissionStatus } from "@/types/mission";
import type { Project } from "@/types/document";
import type { PaginatedResponse } from "@/types/pagination";
import useSWR from "swr";

const PAGE_SIZE = 20;

const MISSION_STATUSES: { value: MissionStatus | "all"; label: string }[] = [
  { value: "all", label: "All Statuses" },
  { value: "draft", label: "Draft" },
  { value: "queued", label: "Queued" },
  { value: "in_progress", label: "In Progress" },
  { value: "completed", label: "Completed" },
  { value: "blocked", label: "Blocked" },
  { value: "cancelled", label: "Cancelled" },
  { value: "validation_failed", label: "Validation Failed" },
];

const STATUS_COLORS: Record<MissionStatus, { bg: string; text: string; dot: string }> = {
  draft: { bg: "bg-surface dark:bg-surface-alt", text: "text-secondary dark:text-secondary", dot: "bg-surface-alt" },
  queued: { bg: "bg-warning-surface dark:bg-warning-surface", text: "text-warning dark:text-warning", dot: "bg-warning" },
  in_progress: { bg: "bg-info-surface dark:bg-info-surface", text: "text-accent-text dark:text-accent-text", dot: "bg-accent" },
  completed: { bg: "bg-success-surface dark:bg-success-surface", text: "text-success dark:text-success", dot: "bg-success" },
  blocked: { bg: "bg-danger-surface dark:bg-danger-surface", text: "text-danger dark:text-danger", dot: "bg-danger" },
  cancelled: { bg: "bg-surface dark:bg-surface-alt", text: "text-muted dark:text-muted", dot: "bg-surface-alt" },
  validation_failed: { bg: "bg-warning-surface dark:bg-warning-surface", text: "text-warning dark:text-warning", dot: "bg-warning" },
};

function StatusBadge({ status }: { status: MissionStatus }) {
  const colors = STATUS_COLORS[status] ?? STATUS_COLORS.draft;
  const label = status.replace("_", " ");

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${colors.bg} ${colors.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${colors.dot}`} />
      {label.charAt(0).toUpperCase() + label.slice(1)}
    </span>
  );
}

function QueuePosition({ position }: { position: number | null }) {
  if (position === null) return null;

  return (
    <span className="inline-flex items-center gap-1 text-xs text-warning dark:text-warning font-medium">
      <span className="text-warning">#</span>
      {position} in queue
    </span>
  );
}

interface MissionCardProps {
  mission: ApiMission;
  queuePosition: number | null;
}

function MissionCard({ mission, queuePosition }: MissionCardProps) {
  const createdAt = mission.created_at
    ? formatDistanceToNow(new Date(mission.created_at), { addSuffix: true })
    : "recently";

  return (
    <Link
      href={`/missions/${mission.id}`}
      className="block bg-surface dark:bg-surface border border-line dark:border-line rounded-lg p-5 hover:border-info-line dark:hover:border-info-line hover:shadow-sm transition-all"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <StatusBadge status={mission.status} />
            <QueuePosition position={queuePosition} />
          </div>
          <h3 className="mt-2 text-lg font-semibold text-foreground dark:text-foreground truncate">
            {mission.title}
          </h3>
          <p className="text-sm text-muted dark:text-muted font-mono">
            {mission.mission_id}
          </p>
        </div>
      </div>

      <p className="mt-3 text-sm text-secondary dark:text-secondary line-clamp-2">
        {mission.objective}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-muted dark:text-muted">
        <span>Created {createdAt}</span>
        {mission.tags.length > 0 && (
          <span className="flex flex-wrap items-center gap-1">
            {mission.tags.slice(0, 3).map((tag) => (
              <span key={tag} className="max-w-full px-1.5 py-0.5 bg-surface dark:bg-surface-alt rounded text-secondary dark:text-secondary">
                {tag}
              </span>
            ))}
            {mission.tags.length > 3 && <span>+{mission.tags.length - 3}</span>}
          </span>
        )}
      </div>

      {mission.error_message && (
        <p className="mt-2 text-xs text-danger dark:text-danger line-clamp-1">
          Error: {mission.error_message}
        </p>
      )}
    </Link>
  );
}

interface PaginationProps {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
}

function Pagination({ page, totalPages, onChange }: PaginationProps) {
  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-between pt-4 text-sm text-secondary dark:text-muted">
      <span>
        Page {page} of {totalPages}
      </span>
      <div className="flex gap-2">
        <button
          onClick={() => onChange(Math.max(1, page - 1))}
          disabled={page === 1}
          className="px-3 py-1.5 border border-line-strong dark:border-line-strong rounded-lg disabled:opacity-40 hover:bg-background dark:hover:bg-surface-alt transition-colors"
        >
          Previous
        </button>
        <button
          onClick={() => onChange(Math.min(totalPages, page + 1))}
          disabled={page >= totalPages}
          className="px-3 py-1.5 border border-line-strong dark:border-line-strong rounded-lg disabled:opacity-40 hover:bg-background dark:hover:bg-surface-alt transition-colors"
        >
          Next
        </button>
      </div>
    </div>
  );
}

function MissionsContent() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<MissionStatus | "all">("all");
  const [projectFilter, setProjectFilter] = useState<string>("all");

  // Fetch projects for filter dropdown
  const { data: projectsData } = useSWR<PaginatedResponse<Project>>(
    ["projects-filter"],
    () => projectsApi.listProjects({ page: 1, pageSize: 100 }),
  );
  const projects = projectsData?.data ?? [];

  // Fetch missions with filters
  const { missions, pagination, isLoading, error, refresh } = useApiMissions({
    page,
    pageSize: PAGE_SIZE,
    status: statusFilter === "all" ? undefined : statusFilter,
    projectId: projectFilter === "all" ? undefined : projectFilter,
  });

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
  }, [statusFilter, projectFilter]);

  const totalPages = pagination?.pages ?? 0;

  return (
    <div className="min-h-screen bg-background dark:bg-background">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-foreground dark:text-foreground">Missions</h1>
            <p className="mt-1 text-secondary dark:text-muted">
              Browse and manage research missions
            </p>
          </div>
          <Link
            href="/missions/new"
            className="inline-flex items-center justify-center px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent transition-colors font-medium text-sm"
          >
            Create Mission
          </Link>
        </header>

        <div className="bg-surface dark:bg-surface border border-line dark:border-line rounded-lg p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
            <div className="flex flex-wrap gap-3">
              <div>
                <label htmlFor="status-filter" className="sr-only">
                  Filter by status
                </label>
                <select
                  id="status-filter"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value as MissionStatus | "all")}
                  className="px-3 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-background text-foreground dark:text-foreground text-sm"
                >
                  {MISSION_STATUSES.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="project-filter" className="sr-only">
                  Filter by project
                </label>
                <select
                  id="project-filter"
                  value={projectFilter}
                  onChange={(e) => setProjectFilter(e.target.value)}
                  className="px-3 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-background text-foreground dark:text-foreground text-sm"
                >
                  <option value="all">All Projects</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <button
              onClick={refresh}
              className="text-sm font-medium text-secondary dark:text-muted hover:text-foreground dark:hover:text-foreground transition-colors"
            >
              Refresh
            </button>
          </div>

          {error && (
            <div className="mb-4 p-4 bg-danger-surface dark:bg-danger-surface border border-danger-line dark:border-danger-line rounded-lg">
              <p className="text-sm text-danger dark:text-danger">
                Failed to load missions: {error.message}
              </p>
            </div>
          )}

          {isLoading && !missions.length ? (
            <div className="py-12 text-center">
              <p className="text-muted dark:text-muted">Loading missions...</p>
            </div>
          ) : missions.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-muted dark:text-muted">
                No missions found. Create one to get started.
              </p>
              <Link
                href="/missions/new"
                className="mt-4 inline-flex items-center text-sm font-medium text-accent-text hover:text-accent-text"
              >
                Create your first mission
              </Link>
            </div>
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {missions.map((mission) => (
                  <MissionCard
                    key={mission.id}
                    mission={mission}
                    queuePosition={calculateQueuePosition(mission, missions)}
                  />
                ))}
              </div>
              <Pagination page={page} totalPages={totalPages} onChange={setPage} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function MissionsPage() {
  return (
    <AuthGate>
      <MissionsContent />
    </AuthGate>
  );
}
