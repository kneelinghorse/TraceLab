/**
 * Console Mission Detail - Mission view with relationships and export.
 */

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/router";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { RelationshipTree } from "@/components/console/RelationshipTree";
import { ExportButtons } from "@/components/console/ExportButtons";
import { StatCard, StatGrid } from "@/components/console/StatCard";
import { missionsApi } from "@/lib/api/missions";
import { getRelationshipContext } from "@/lib/api/console";
import type { ApiMission } from "@/types/mission";
import type { RelationshipContextResponse } from "@/types/console";

function MissionDetailContent() {
  const router = useRouter();
  const { id } = router.query;

  const [mission, setMission] = useState<ApiMission | null>(null);
  const [relationships, setRelationships] = useState<RelationshipContextResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!id || typeof id !== "string") return;

    try {
      setIsLoading(true);
      setError(null);

      const missionData = await missionsApi.get(id);
      setMission(missionData);

      // Try to load relationships (may fail if not available)
      try {
        const relData = await getRelationshipContext(id, { depth: 2 });
        setRelationships(relData);
      } catch {
        // Relationships not available for this mission
        setRelationships(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load mission");
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (isLoading) {
    return (
      <main className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-center py-12">
            <div className="text-gray-500 dark:text-gray-400">Loading mission...</div>
          </div>
        </div>
      </main>
    );
  }

  if (error || !mission) {
    return (
      <main className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-800 dark:text-red-200">
            {error ?? "Mission not found"}
          </div>
          <Link
            href="/console/missions"
            className="mt-4 inline-block text-blue-600 dark:text-blue-400 hover:underline"
          >
            Back to missions
          </Link>
        </div>
      </main>
    );
  }

  const successCriteriaCount = mission.success_criteria?.length ?? 0;
  const deliverablesCount = mission.deliverables?.length ?? 0;
  const tagsCount = mission.tags?.length ?? 0;
  const hasError = !!mission.error_message;
  const hasResult = !!mission.result_markdown || !!mission.result_report_id;

  return (
    <main className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Breadcrumb */}
        <nav className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          <Link href="/console" className="hover:text-gray-700 dark:hover:text-gray-200">
            Console
          </Link>
          {" / "}
          <Link href="/console/missions" className="hover:text-gray-700 dark:hover:text-gray-200">
            Missions
          </Link>
          {" / "}
          <span className="text-gray-900 dark:text-white">{mission.mission_id ?? id}</span>
        </nav>

        {/* Header */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
              {mission.title ?? "Untitled Mission"}
            </h1>
            <p className="mt-2 text-gray-600 dark:text-gray-400">
              {mission.mission_id}
            </p>
          </div>
          <div className="flex items-center gap-4">
            <ExportButtons mission={mission} relationships={relationships} />
            <span
              className={`text-sm px-3 py-1.5 rounded-full ${
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
              <span className="text-sm px-3 py-1.5 rounded-full bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
                error
              </span>
            )}
          </div>
        </div>

        {/* Stats */}
        <section className="mb-8">
          <StatGrid columns={4}>
            <StatCard
              label="Status"
              value={mission.status ?? "draft"}
              color={
                mission.status === "completed"
                  ? "green"
                  : mission.status === "in_progress"
                  ? "yellow"
                  : mission.status === "blocked"
                  ? "red"
                  : "default"
              }
            />
            <StatCard
              label="Success Criteria"
              value={successCriteriaCount}
              sublabel="defined"
              color="blue"
            />
            <StatCard
              label="Deliverables"
              value={deliverablesCount}
              sublabel="expected"
              color="purple"
            />
            <StatCard
              label="Tags"
              value={tagsCount}
              color="default"
            />
          </StatGrid>
        </section>

        {/* Objective */}
        {mission.objective && (
          <section className="mb-8 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Objective
            </h2>
            <p className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
              {mission.objective}
            </p>
          </section>
        )}

        {/* Success Criteria */}
        {successCriteriaCount > 0 && (
          <section className="mb-8 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Success Criteria
            </h2>
            <ul className="space-y-2">
              {mission.success_criteria.map((criterion, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-green-500 mt-1">✓</span>
                  <span className="text-gray-700 dark:text-gray-300">{criterion}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Deliverables */}
        {deliverablesCount > 0 && (
          <section className="mb-8 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Deliverables
            </h2>
            <ul className="space-y-2">
              {mission.deliverables.map((deliverable, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-blue-500 mt-1">•</span>
                  <span className="text-gray-700 dark:text-gray-300">{deliverable}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Tags */}
        {tagsCount > 0 && (
          <section className="mb-8 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Tags
            </h2>
            <div className="flex flex-wrap gap-2">
              {mission.tags.map((tag, idx) => (
                <span
                  key={idx}
                  className="px-3 py-1 bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300 rounded-full text-sm"
                >
                  {tag}
                </span>
              ))}
            </div>
          </section>
        )}

        {/* Error Message */}
        {hasError && (
          <section className="mb-8 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-red-800 dark:text-red-200 mb-4">
              Error
            </h2>
            <p className="text-red-700 dark:text-red-300 whitespace-pre-wrap">
              {mission.error_message}
            </p>
          </section>
        )}

        {/* Result Markdown */}
        {mission.result_markdown && (
          <section className="mb-8 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Result
            </h2>
            <div className="prose dark:prose-invert max-w-none">
              <pre className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700 p-4 rounded-lg overflow-auto max-h-96">
                {mission.result_markdown}
              </pre>
            </div>
          </section>
        )}

        {/* Relationships */}
        {relationships && (
          <section className="mb-8">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Relationships
            </h2>
            <RelationshipTree relationships={relationships} />
          </section>
        )}

        {/* Metadata */}
        <section className="text-sm text-gray-500 dark:text-gray-400 space-y-1">
          <p>Created: {new Date(mission.created_at).toLocaleString()}</p>
          <p>Updated: {new Date(mission.updated_at).toLocaleString()}</p>
          {mission.queued_at && <p>Queued: {new Date(mission.queued_at).toLocaleString()}</p>}
          {mission.started_at && <p>Started: {new Date(mission.started_at).toLocaleString()}</p>}
          {mission.completed_at && <p>Completed: {new Date(mission.completed_at).toLocaleString()}</p>}
          {mission.created_by && <p>Created by: {mission.created_by}</p>}
        </section>
      </div>
    </main>
  );
}

export default function MissionDetailPage() {
  return (
    <AuthGate>
      <MissionDetailContent />
    </AuthGate>
  );
}
