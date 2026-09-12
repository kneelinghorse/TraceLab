/**
 * Console Mission Detail - Mission view with relationships and export.
 */

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/router";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
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
      <div className="min-h-screen bg-background dark:bg-background py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-center py-12">
            <div className="text-muted dark:text-muted">Loading mission...</div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !mission) {
    return (
      <div className="min-h-screen bg-background dark:bg-background py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="p-4 bg-danger-surface dark:bg-danger-surface border border-danger-line dark:border-danger-line rounded-lg text-danger dark:text-danger">
            {error ?? "Mission not found"}
          </div>
          <Link
            href="/console/missions"
            className="mt-4 inline-block text-accent-text dark:text-accent-text underline underline-offset-4"
          >
            Back to missions
          </Link>
        </div>
      </div>
    );
  }

  const successCriteriaCount = mission.success_criteria?.length ?? 0;
  const deliverablesCount = mission.deliverables?.length ?? 0;
  const tagsCount = mission.tags?.length ?? 0;
  const hasError = !!mission.error_message;
  const hasResult = !!mission.result_markdown || !!mission.result_report_id;

  return (
    <div className="min-h-screen bg-background dark:bg-background py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Breadcrumb */}
        <nav className="text-sm text-muted dark:text-muted mb-4">
          <Link href="/console" className="hover:text-secondary dark:hover:text-secondary">
            Console
          </Link>
          {" / "}
          <Link href="/console/missions" className="hover:text-secondary dark:hover:text-secondary">
            Missions
          </Link>
          {" / "}
          <span className="text-foreground dark:text-foreground">{mission.mission_id ?? id}</span>
        </nav>

        {/* Header */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-foreground dark:text-foreground">
              {mission.title ?? "Untitled Mission"}
            </h1>
            <p className="mt-2 text-secondary dark:text-muted">
              {mission.mission_id}
            </p>
          </div>
          <div className="flex items-center gap-4">
            <ExportButtons mission={mission} relationships={relationships} />
            <span
              className={`text-sm px-3 py-1.5 rounded-full ${
                mission.status === "completed"
                  ? "bg-success-surface text-success dark:bg-success-surface dark:text-success"
                  : mission.status === "in_progress"
                  ? "bg-warning-surface text-warning dark:bg-warning-surface dark:text-warning"
                  : mission.status === "queued"
                  ? "bg-info-surface text-info dark:bg-info-surface dark:text-info"
                  : mission.status === "blocked"
                  ? "bg-danger-surface text-danger dark:bg-danger-surface dark:text-danger"
                  : "bg-surface text-foreground dark:bg-surface-alt dark:text-secondary"
              }`}
            >
              {mission.status ?? "draft"}
            </span>
            {hasError && (
              <span className="text-sm px-3 py-1.5 rounded-full bg-danger-surface text-danger dark:bg-danger-surface dark:text-danger">
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
          <section className="mb-8 bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6">
            <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">
              Objective
            </h2>
            <p className="text-secondary dark:text-secondary whitespace-pre-wrap">
              {mission.objective}
            </p>
          </section>
        )}

        {/* Success Criteria */}
        {successCriteriaCount > 0 && (
          <section className="mb-8 bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6">
            <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">
              Success Criteria
            </h2>
            <ul className="space-y-2">
              {mission.success_criteria.map((criterion, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-success mt-1">✓</span>
                  <span className="text-secondary dark:text-secondary">{criterion}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Deliverables */}
        {deliverablesCount > 0 && (
          <section className="mb-8 bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6">
            <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">
              Deliverables
            </h2>
            <ul className="space-y-2">
              {mission.deliverables.map((deliverable, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-accent-text mt-1">•</span>
                  <span className="text-secondary dark:text-secondary">{deliverable}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Tags */}
        {tagsCount > 0 && (
          <section className="mb-8 bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6">
            <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">
              Tags
            </h2>
            <div className="flex flex-wrap gap-2">
              {mission.tags.map((tag, idx) => (
                <span
                  key={idx}
                  className="px-3 py-1 bg-surface text-secondary dark:bg-surface-alt dark:text-secondary rounded-full text-sm"
                >
                  {tag}
                </span>
              ))}
            </div>
          </section>
        )}

        {/* Error Message */}
        {hasError && (
          <section className="mb-8 bg-danger-surface dark:bg-danger-surface border border-danger-line dark:border-danger-line rounded-lg p-6">
            <h2 className="text-lg font-semibold text-danger dark:text-danger mb-4">
              Error
            </h2>
            <p className="text-danger dark:text-danger whitespace-pre-wrap">
              {mission.error_message}
            </p>
          </section>
        )}

        {/* Result Markdown */}
        {mission.result_markdown && (
          <section className="mb-8 bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-6">
            <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">
              Result
            </h2>
            <MarkdownRenderer content={mission.result_markdown} />
          </section>
        )}

        {/* Relationships */}
        {relationships && (
          <section className="mb-8">
            <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">
              Relationships
            </h2>
            <RelationshipTree relationships={relationships} />
          </section>
        )}

        {/* Metadata */}
        <section className="text-sm text-muted dark:text-muted space-y-1">
          <p>Created: {new Date(mission.created_at).toLocaleString()}</p>
          <p>Updated: {new Date(mission.updated_at).toLocaleString()}</p>
          {mission.queued_at && <p>Queued: {new Date(mission.queued_at).toLocaleString()}</p>}
          {mission.started_at && <p>Started: {new Date(mission.started_at).toLocaleString()}</p>}
          {mission.completed_at && <p>Completed: {new Date(mission.completed_at).toLocaleString()}</p>}
          {mission.created_by && <p>Created by: {mission.created_by}</p>}
        </section>
      </div>
    </div>
  );
}

export default function MissionDetailPage() {
  return (
    <AuthGate>
      <MissionDetailContent />
    </AuthGate>
  );
}
