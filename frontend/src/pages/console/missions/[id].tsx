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
import { fetchMission } from "@/lib/api/missions";
import { getRelationshipContext } from "@/lib/api/console";
import type { Mission } from "@/types/mission";
import type { RelationshipContextResponse } from "@/types/console";

function MissionDetailContent() {
  const router = useRouter();
  const { id } = router.query;

  const [mission, setMission] = useState<Mission | null>(null);
  const [relationships, setRelationships] = useState<RelationshipContextResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!id || typeof id !== "string") return;

    try {
      setIsLoading(true);
      setError(null);

      const missionData = await fetchMission(id);
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

  const { mission_data } = mission;
  const gates = mission_data?.quality_checkpoints ?? [];
  const passingGates = gates.filter((g) => g.status === "pass").length;
  const failingGates = gates.filter((g) => g.status === "fail").length;
  const evidenceCount = mission_data?.evidence?.length ?? 0;
  const linkedEvidence = mission_data?.evidence?.filter((e) => e.chunk_id).length ?? 0;

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
          <span className="text-gray-900 dark:text-white">{mission_data?.mission_id ?? id}</span>
        </nav>

        {/* Header */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
              {mission_data?.title ?? "Untitled Mission"}
            </h1>
            <p className="mt-2 text-gray-600 dark:text-gray-400">
              {mission_data?.mission_id}
            </p>
          </div>
          <div className="flex items-center gap-4">
            <ExportButtons mission={mission} relationships={relationships} />
            <span
              className={`text-sm px-3 py-1.5 rounded-full ${
                mission_data?.status === "complete"
                  ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                  : mission_data?.status === "in_progress"
                  ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
                  : mission_data?.status === "review"
                  ? "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200"
                  : "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200"
              }`}
            >
              {mission_data?.status ?? "draft"}
            </span>
          </div>
        </div>

        {/* Stats */}
        <section className="mb-8">
          <StatGrid columns={4}>
            <StatCard
              label="Completion"
              value={`${mission.completion_percentage ?? 0}%`}
              color={
                (mission.completion_percentage ?? 0) >= 80
                  ? "green"
                  : (mission.completion_percentage ?? 0) >= 60
                  ? "blue"
                  : (mission.completion_percentage ?? 0) >= 40
                  ? "yellow"
                  : "red"
              }
            />
            <StatCard
              label="Evidence Items"
              value={evidenceCount}
              sublabel={`${linkedEvidence} linked`}
              color="blue"
            />
            <StatCard
              label="Passing Gates"
              value={passingGates}
              sublabel={`of ${gates.length}`}
              color="green"
            />
            <StatCard
              label="Failing Gates"
              value={failingGates}
              sublabel={`of ${gates.length}`}
              color={failingGates > 0 ? "red" : "default"}
            />
          </StatGrid>
        </section>

        {/* Research Statement */}
        {mission_data?.research_statement && (
          <section className="mb-8 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Research Statement
            </h2>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">
                  Topic
                </h3>
                <p className="text-gray-900 dark:text-white">
                  {mission_data.research_statement.topic}
                </p>
              </div>
              <div>
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">
                  Objective
                </h3>
                <p className="text-gray-900 dark:text-white">
                  {mission_data.research_statement.objective}
                </p>
              </div>
              <div className="md:col-span-2">
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">
                  Scope
                </h3>
                <p className="text-gray-900 dark:text-white">
                  {mission_data.research_statement.scope}
                </p>
              </div>
            </div>
          </section>
        )}

        {/* Quality Gates */}
        {gates.length > 0 && (
          <section className="mb-8 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Quality Gates
            </h2>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {gates.map((gate, idx) => (
                <div
                  key={idx}
                  className={`p-4 rounded-lg border ${
                    gate.status === "pass"
                      ? "bg-green-50 border-green-200 dark:bg-green-900/20 dark:border-green-800"
                      : gate.status === "fail"
                      ? "bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-800"
                      : "bg-gray-50 border-gray-200 dark:bg-gray-700 dark:border-gray-600"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-gray-900 dark:text-white">
                      {gate.gate.replace(/_/g, " ")}
                    </span>
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        gate.status === "pass"
                          ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                          : gate.status === "fail"
                          ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                          : "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200"
                      }`}
                    >
                      {gate.status}
                    </span>
                  </div>
                  {gate.notes && (
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {gate.notes}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Evidence */}
        {evidenceCount > 0 && (
          <section className="mb-8 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Evidence ({evidenceCount})
            </h2>
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {mission_data?.evidence?.map((ev, idx) => (
                <div
                  key={idx}
                  className="p-4 bg-gray-50 dark:bg-gray-700 rounded-lg"
                >
                  <div className="flex items-start justify-between mb-2">
                    <span className="font-medium text-gray-900 dark:text-white">
                      {ev.evidence_id}
                    </span>
                    {ev.chunk_id ? (
                      <span className="text-xs px-2 py-0.5 bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 rounded">
                        Linked
                      </span>
                    ) : (
                      <span className="text-xs px-2 py-0.5 bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200 rounded">
                        Pending
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-300 mb-2">
                    {ev.summary}
                  </p>
                  <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                    <span>Source: {ev.source}</span>
                    {ev.relevance_score !== null && ev.relevance_score !== undefined && (
                      <span>Relevance: {Math.round(ev.relevance_score * 100)}%</span>
                    )}
                  </div>
                </div>
              ))}
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

        {/* Synthesis */}
        {mission_data?.synthesis && (
          <section className="mb-8 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Synthesis
            </h2>
            <div className="space-y-4">
              {mission_data.synthesis.key_insights?.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Key Insights
                  </h3>
                  <ul className="list-disc list-inside text-gray-600 dark:text-gray-400 space-y-1">
                    {mission_data.synthesis.key_insights.map((insight, idx) => (
                      <li key={idx}>{insight}</li>
                    ))}
                  </ul>
                </div>
              )}
              {mission_data.synthesis.recommendations?.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Recommendations
                  </h3>
                  <ul className="list-disc list-inside text-gray-600 dark:text-gray-400 space-y-1">
                    {mission_data.synthesis.recommendations.map((rec, idx) => (
                      <li key={idx}>{rec}</li>
                    ))}
                  </ul>
                </div>
              )}
              {mission_data.synthesis.next_steps?.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Next Steps
                  </h3>
                  <ul className="list-disc list-inside text-gray-600 dark:text-gray-400 space-y-1">
                    {mission_data.synthesis.next_steps.map((step, idx) => (
                      <li key={idx}>{step}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Metadata */}
        <section className="text-sm text-gray-500 dark:text-gray-400">
          <p>Created: {new Date(mission.created_at).toLocaleString()}</p>
          <p>Updated: {new Date(mission.updated_at).toLocaleString()}</p>
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
