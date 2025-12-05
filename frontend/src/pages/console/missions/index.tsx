/**
 * Console Missions List - Browse and filter all missions.
 */

import { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { getConsoleMissions } from "@/lib/api/console";
import type { Mission, MissionStatus } from "@/types/mission";

type SortField = "updated_at" | "created_at" | "completion_percentage" | "title";
type SortDirection = "asc" | "desc";

interface FilterState {
  status: MissionStatus | "all";
  search: string;
  qualityRange: "all" | "excellent" | "good" | "fair" | "poor";
}

function MissionListContent() {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    status: "all",
    search: "",
    qualityRange: "all",
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
        // Status filter
        if (filters.status !== "all" && m.mission_data?.status !== filters.status) {
          return false;
        }

        // Search filter
        if (filters.search) {
          const searchLower = filters.search.toLowerCase();
          const title = m.mission_data?.title?.toLowerCase() ?? "";
          const missionId = m.mission_data?.mission_id?.toLowerCase() ?? "";
          if (!title.includes(searchLower) && !missionId.includes(searchLower)) {
            return false;
          }
        }

        // Quality range filter
        if (filters.qualityRange !== "all") {
          const completion = m.completion_percentage ?? 0;
          switch (filters.qualityRange) {
            case "excellent":
              if (completion < 80) return false;
              break;
            case "good":
              if (completion < 60 || completion >= 80) return false;
              break;
            case "fair":
              if (completion < 40 || completion >= 60) return false;
              break;
            case "poor":
              if (completion >= 40) return false;
              break;
          }
        }

        return true;
      })
      .sort((a, b) => {
        let aVal: string | number;
        let bVal: string | number;

        switch (sort.field) {
          case "title":
            aVal = a.mission_data?.title ?? "";
            bVal = b.mission_data?.title ?? "";
            break;
          case "completion_percentage":
            aVal = a.completion_percentage ?? 0;
            bVal = b.completion_percentage ?? 0;
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
      const status = m.mission_data?.status ?? "unknown";
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
                <option value="in_progress">In Progress ({statusCounts.in_progress ?? 0})</option>
                <option value="review">Review ({statusCounts.review ?? 0})</option>
                <option value="complete">Complete ({statusCounts.complete ?? 0})</option>
              </select>
            </div>

            {/* Quality Filter */}
            <div className="w-48">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Quality
              </label>
              <select
                value={filters.qualityRange}
                onChange={(e) => setFilters((f) => ({ ...f, qualityRange: e.target.value as FilterState["qualityRange"] }))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="all">All</option>
                <option value="excellent">Excellent (80-100%)</option>
                <option value="good">Good (60-79%)</option>
                <option value="fair">Fair (40-59%)</option>
                <option value="poor">Poor (0-39%)</option>
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
                    <th
                      className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                      onClick={() => handleSort("completion_percentage")}
                    >
                      Completion {sort.field === "completion_percentage" && (sort.direction === "asc" ? "↑" : "↓")}
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                      Quality Gates
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
                    const gates = mission.mission_data?.quality_checkpoints ?? [];
                    const passingGates = gates.filter((g) => g.status === "pass").length;
                    const failingGates = gates.filter((g) => g.status === "fail").length;
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
                            {mission.mission_data?.title ?? mission.mission_data?.mission_id ?? "Untitled"}
                          </Link>
                          <div className="text-sm text-gray-500 dark:text-gray-400">
                            {mission.mission_data?.mission_id}
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <span
                            className={`text-xs px-2 py-1 rounded-full ${
                              mission.mission_data?.status === "complete"
                                ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                                : mission.mission_data?.status === "in_progress"
                                ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
                                : mission.mission_data?.status === "review"
                                ? "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200"
                                : "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200"
                            }`}
                          >
                            {mission.mission_data?.status ?? "draft"}
                          </span>
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-2">
                            <div className="w-24 h-2 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
                              <div
                                className={`h-full rounded-full ${
                                  (mission.completion_percentage ?? 0) >= 80
                                    ? "bg-green-500"
                                    : (mission.completion_percentage ?? 0) >= 60
                                    ? "bg-blue-500"
                                    : (mission.completion_percentage ?? 0) >= 40
                                    ? "bg-yellow-500"
                                    : "bg-red-500"
                                }`}
                                style={{ width: `${mission.completion_percentage ?? 0}%` }}
                              />
                            </div>
                            <span className="text-sm text-gray-600 dark:text-gray-300">
                              {mission.completion_percentage ?? 0}%
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-2">
                            {passingGates > 0 && (
                              <span className="text-xs px-2 py-0.5 bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 rounded">
                                {passingGates} pass
                              </span>
                            )}
                            {failingGates > 0 && (
                              <span className="text-xs px-2 py-0.5 bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 rounded">
                                {failingGates} fail
                              </span>
                            )}
                            {gates.length === 0 && (
                              <span className="text-xs text-gray-400 dark:text-gray-500">
                                No gates
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
