/**
 * Console Missions List - Browse and filter all missions.
 */

import { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { getConsoleMissions } from "@/lib/api/console";
import type { ApiMission, MissionStatus } from "@/types/mission";

type SortField = "updated_at" | "created_at" | "title";
type SortDirection = "asc" | "desc";

interface FilterState {
  status: MissionStatus | "all";
  search: string;
}

function MissionListContent() {
  const [missions, setMissions] = useState<ApiMission[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    status: "all",
    search: "",
  });
  const [sort, setSort] = useState<{ field: SortField; direction: SortDirection }>({
    field: "updated_at",
    direction: "desc",
  });

  const loadMissions = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await getConsoleMissions();
      setMissions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load missions");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMissions();
  }, [loadMissions]);

  const filteredMissions = useMemo(() => {
    return missions
      .filter((m) => {
        // Status filter - status is directly on ApiMission
        if (filters.status !== "all" && m.status !== filters.status) {
          return false;
        }

        // Search filter
        if (filters.search) {
          const searchLower = filters.search.toLowerCase();
          const title = m.title?.toLowerCase() ?? "";
          const missionId = m.mission_id?.toLowerCase() ?? "";
          const objective = m.objective?.toLowerCase() ?? "";
          if (!title.includes(searchLower) && !missionId.includes(searchLower) && !objective.includes(searchLower)) {
            return false;
          }
        }

        return true;
      })
      .sort((a, b) => {
        let aVal: string | number;
        let bVal: string | number;

        switch (sort.field) {
          case "title":
            aVal = a.title ?? "";
            bVal = b.title ?? "";
            break;
          case "created_at":
            aVal = new Date(a.created_at).getTime();
            bVal = new Date(b.created_at).getTime();
            break;
          case "updated_at":
          default:
            aVal = new Date(a.updated_at).getTime();
            bVal = new Date(b.updated_at).getTime();
            break;
        }

        const comparison = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
        return sort.direction === "asc" ? comparison : -comparison;
      });
  }, [missions, filters, sort]);

  const handleSort = (field: SortField) => {
    setSort((prev) => ({
      field,
      direction: prev.field === field && prev.direction === "desc" ? "asc" : "desc",
    }));
  };

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { all: missions.length };
    for (const m of missions) {
      const status = m.status ?? "draft";
      counts[status] = (counts[status] ?? 0) + 1;
    }
    return counts;
  }, [missions]);

  return (
    <main className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <nav className="text-sm text-gray-500 dark:text-gray-400 mb-2">
              <Link href="/console" className="hover:text-gray-700 dark:hover:text-gray-200">
                Console
              </Link>
              {" / "}
              <span className="text-gray-900 dark:text-white">Missions</span>
            </nav>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
              Mission List
            </h1>
          </div>
          <button
            onClick={loadMissions}
            disabled={isLoading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            Refresh
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-800 dark:text-red-200">
            {error}
          </div>
        )}

        {/* Filters */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 mb-6">
          <div className="flex flex-wrap gap-4">
            {/* Search */}
            <div className="flex-1 min-w-[200px]">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Search
              </label>
              <input
                type="text"
                placeholder="Search by title or ID..."
                value={filters.search}
                onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            {/* Status Filter */}
            <div className="w-48">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Status
              </label>
              <select
                value={filters.status}
                onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value as MissionStatus | "all" }))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="all">All ({statusCounts.all})</option>
                <option value="draft">Draft ({statusCounts.draft ?? 0})</option>
                <option value="queued">Queued ({statusCounts.queued ?? 0})</option>
                <option value="in_progress">In Progress ({statusCounts.in_progress ?? 0})</option>
                <option value="completed">Completed ({statusCounts.completed ?? 0})</option>
                <option value="blocked">Blocked ({statusCounts.blocked ?? 0})</option>
                <option value="validation_failed">Validation Failed ({statusCounts.validation_failed ?? 0})</option>
              </select>
            </div>
          </div>
        </div>

        {/* Results Count */}
        <div className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          Showing {filteredMissions.length} of {missions.length} missions
        </div>

        {/* Mission Table */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-gray-500 dark:text-gray-400">Loading missions...</div>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 dark:bg-gray-700">
                  <tr>
                    <th
                      className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                      onClick={() => handleSort("title")}
                    >
                      Title {sort.field === "title" && (sort.direction === "asc" ? "↑" : "↓")}
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                      Objective
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                      Tags
                    </th>
                    <th
                      className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                      onClick={() => handleSort("updated_at")}
                    >
                      Updated {sort.field === "updated_at" && (sort.direction === "asc" ? "↑" : "↓")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {filteredMissions.map((mission) => {
                    const hasError = !!mission.error_message;
                    return (
                      <tr
                        key={mission.id}
                        className="hover:bg-gray-50 dark:hover:bg-gray-700"
                      >
                        <td className="px-4 py-4">
                          <Link
                            href={`/console/missions/${mission.id}`}
                            className="font-medium text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400"
                          >
                            {mission.title ?? mission.mission_id ?? "Untitled"}
                          </Link>
                          <div className="text-sm text-gray-500 dark:text-gray-400">
                            {mission.mission_id}
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <span
                            className={`text-xs px-2 py-1 rounded-full ${
                              mission.status === "completed"
                                ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                                : mission.status === "in_progress"
                                ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
                                : mission.status === "queued"
                                ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                                : mission.status === "blocked"
                                ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                                : "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200"
                            }`}
                          >
                            {mission.status ?? "draft"}
                          </span>
                          {hasError && (
                            <span className="ml-2 text-xs px-2 py-1 rounded-full bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
                              error
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-4">
                          <p className="text-sm text-gray-600 dark:text-gray-300 max-w-xs truncate">
                            {mission.objective ?? "No objective"}
                          </p>
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex flex-wrap gap-1">
                            {(mission.tags ?? []).slice(0, 3).map((tag) => (
                              <span
                                key={tag}
                                className="text-xs px-2 py-0.5 bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300 rounded"
                              >
                                {tag}
                              </span>
                            ))}
                            {(mission.tags?.length ?? 0) > 3 && (
                              <span className="text-xs text-gray-400 dark:text-gray-500">
                                +{mission.tags!.length - 3}
                              </span>
                            )}
                            {(mission.tags?.length ?? 0) === 0 && (
                              <span className="text-xs text-gray-400 dark:text-gray-500">
                                No tags
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-4 text-sm text-gray-500 dark:text-gray-400">
                          {new Date(mission.updated_at).toLocaleDateString()}
                        </td>
                      </tr>
                    );
                  })}
                  {filteredMissions.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                        No missions match your filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

export default function MissionsListPage() {
  return (
    <AuthGate>
      <MissionListContent />
    </AuthGate>
  );
}
