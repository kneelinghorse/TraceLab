import { RelationshipLink } from "@/components/graph/RelationshipLink";
import { parseApiTimestamp } from "@/lib/api/timestamps";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { HttpError } from "@/lib/api/http";
import { PageState } from "@/components/ui/PageState";
import { useFeedback } from "@/components/ui/useFeedback";
import { MissionRunActivity } from "@/components/missions/MissionRunActivity";
import { missionOccurredAt } from "@/lib/api/activity";
import { markViewed } from "@/lib/hooks/useActivitySummary";
import { apiErrorMessage } from "@/lib/api/errors";
import { Dialog } from "@/components/ui/Dialog";
import { EvidencePanel } from "@/components/evidence/EvidencePanel";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { formatDistanceToNow } from "date-fns";

import { AuthGate } from "@/components/AuthGate";
import { LibrarianSteps } from "@/components/librarian/LibrarianSteps";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { useAuth } from "@/contexts/AuthContext";
import { readOrientationDismissed, writeOrientationDismissed } from "@/lib/librarian/storage";
import { ContractPreviewPanel, ExecutionTimeline, ResearchPhases, ResultLinks, MissionForm } from "@/components/missions";
import { downloadFile } from "@/lib/api/console";
import { missionsApi } from "@/lib/api/missions";
import { useApiMission } from "@/lib/hooks/useMissions";
import type { ReportPromotionResponse } from "@/types/mission";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="p-6 border-b border-line last:border-b-0">
      <h2 className="text-lg font-semibold text-foreground mb-4">{title}</h2>
      {children}
    </div>
  );
}

function MissionDetailContent() {
  const router = useRouter();
  const missionId = typeof router.query.id === "string" ? router.query.id : undefined;
  // The tab lives in the URL so a Results view can be linked, reloaded and captured by the
  // route baseline, which previously could only ever photograph the Run tab (next-step #340).
  // The URL is the entry point and local state is the interaction state: router.replace is
  // async, so deriving the tab from the query alone would lag visibly on every click.
  const urlTab = MISSION_TABS.includes(router.query.tab as MissionTab) ? (router.query.tab as MissionTab) : "overview";
  const [detailTab, setTab] = useState<MissionTab>(urlTab);
  useEffect(() => { setTab(urlTab); }, [urlTab]);
  const setDetailTab = useCallback((tab: string) => {
    setTab(tab as MissionTab);
    // Keep the default view's URL clean; other params (filters, anchors) survive. Setting
    // tab to undefined is not enough: Next keeps the key and emits a bare "?tab=".
    const query: typeof router.query = Object.fromEntries(
      Object.entries(router.query).filter(([key]) => key !== "tab"),
    );
    if (tab !== "overview") query.tab = tab;
    void router.replace?.({ pathname: router.pathname, query }, undefined, { shallow: true });
  }, [router]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isPromoting, setIsPromoting] = useState(false);
  const [promotionResult, setPromotionResult] = useState<ReportPromotionResponse | null>(null);
  const [promotionError, setPromotionError] = useState<string | null>(null);

  const [isEditing, setIsEditing] = useState(false);
  const [acting, setActing] = useState(false);
  const { askConfirmation, notify, feedback } = useFeedback();
  const { mission, isLoading, error, refresh } = useApiMission(missionId);
  // A draft reached from the Librarian gets one orienting notice (LIB-2, decision #527):
  // the create-then-submit shape is deliberate, so it is explained rather than removed.
  const { user } = useAuth();
  const fromLibrarian = router.query.from === "librarian";
  const [orientationHidden, setOrientationHidden] = useState(true);
  useEffect(() => { setOrientationHidden(readOrientationDismissed(user?.user_id)); }, [user?.user_id]);
  const dismissOrientation = () => { writeOrientationDismissed(user?.user_id); setOrientationHidden(true); };
  const occurredAt = mission ? missionOccurredAt(mission) : null;
  useEffect(() => {
    // Opening a mission marks it viewed at its current revision (decision #459).
    if (mission && occurredAt) void markViewed([{ type: "mission", id: mission.id, occurred_at: occurredAt }]);
  }, [mission?.id, occurredAt]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmitToDeepSearch = async () => {
    if (!missionId) return;

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await missionsApi.submitToDeepSearch(missionId);
      refresh();
    } catch (err) {
      setSubmitError(apiErrorMessage(err, "Failed to submit mission"));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!missionId) return;
    setDeleting(true);
    setActionError(null);

    try {
      await missionsApi.delete(missionId);
      router.push("/missions");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to delete mission");
    } finally {
      setDeleting(false);
    }
  };

  const handlePromoteReport = async () => {
    if (!missionId) return;

    setIsPromoting(true);
    setPromotionError(null);
    setPromotionResult(null);

    try {
      const result = await missionsApi.promoteReport(missionId);
      setPromotionResult(result);
      refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to promote report";
      // Check for already promoted error (409)
      if (message.includes("already been promoted")) {
        setPromotionError("Report has already been promoted to a document.");
      } else {
        setPromotionError(message);
      }
    } finally {
      setIsPromoting(false);
    }
  };

  const handleCancelRun = async () => {
    if (!mission || !await askConfirmation("Cancel this mission? Existing results and evidence will remain available.")) return;
    setActing(true);
    try {
      await missionsApi.update(mission.id, { status: "cancelled" });
      await refresh();
      notify("Mission cancelled", "success");
    } catch (err) { notify(err); } finally { setActing(false); }
  };
  const handleRerun = async () => {
    if (!mission || !await askConfirmation("Prepare another run with a new mission ID? Review the copied inputs before submitting; this run stays unchanged.")) return;
    void router.push({ pathname: "/missions/new", query: { from: mission.id } });
  };

  if (!missionId) {
    return (
      <div className="min-h-screen bg-background py-8">
        <div className="max-w-4xl mx-auto px-4">
          <p className="text-secondary">Select a mission to view details.</p>
        </div>
      </div>
    );
  }

  if (isLoading) return <PageState state="loading" title="Loading mission…" />;
  if (error instanceof HttpError && error.status === 404) return <PageState state="empty" title="Mission not found."><Link href="/missions">Back to missions</Link></PageState>;
  if (error) return <PageState state="error" title="Mission could not load." onRetry={() => void refresh()} />;
  if (!mission) return <PageState state="empty" title="Mission not found." />;

  const createdAt = mission.created_at
    ? formatDistanceToNow(parseApiTimestamp(mission.created_at), { addSuffix: true })
    : null;
  const isDraft = mission.status === "draft";
  const hasResearchPhases = Object.keys(mission.research_phases).length > 0;

  return (
    <div className="min-h-screen bg-background py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {feedback}
          {isDraft && fromLibrarian && !orientationHidden && (
            <section aria-label="Next step" className="mb-6 space-y-3 rounded-xl border border-info-line bg-info-surface p-4">
              <p className="text-sm text-info">
                <span className="font-semibold">This is a saved draft.</span> Nothing runs until you press Submit to DeepSearch. Edit it first if you like, or come back and submit it later; it waits here.
              </p>
              <LibrarianSteps current={3} onDismiss={dismissOrientation} />
            </section>
          )}
          {actionError && !deleteOpen && <p role="alert" className="mb-4 break-words rounded bg-danger-surface p-4 text-danger">{actionError}</p>}
          <Dialog open={deleteOpen} title="Delete mission" onClose={() => { if (!deleting) setDeleteOpen(false); }}>
            <p className="mb-4">Delete this mission? This cannot be undone.</p>
            {actionError && <p role="alert" className="mb-4 break-words text-danger">{actionError}</p>}
            <div className="flex gap-3"><button disabled={deleting} className="rounded border border-line px-3 py-2" onClick={() => setDeleteOpen(false)}>Cancel</button><button disabled={deleting} className="rounded bg-danger-surface px-3 py-2 text-danger" onClick={() => void handleDelete()}>{deleting ? "Deleting…" : "Delete mission"}</button></div>
          </Dialog>
        <div className="mb-6 flex items-center justify-between">
          <Link
            href="/missions"
            className="inline-flex items-center text-sm text-accent-text hover:text-accent-text"
          >
            &larr; Back to missions
          </Link>
          <div className="flex items-center gap-2">
            <button
              onClick={refresh}
              className="px-3 py-1.5 text-sm text-secondary hover:text-foreground border border-line-strong rounded-lg"
            >
              Refresh
            </button>
          </div>
        </div>

        <div className="bg-surface border border-line rounded-lg overflow-hidden">
          {/* Header Section */}
          <div className="p-6 border-b border-line">
            {isEditing ? (
              <div><h1 className="mb-4 text-2xl font-semibold">Edit mission</h1><MissionForm source={mission} mode="edit" onCancel={() => { setIsEditing(false); void refresh(); }} onSuccess={() => { setIsEditing(false); void refresh(); }} /></div>
            ) : (
              /* View Mode */
              <>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-3 mb-2">
                      <StatusBadge status={mission.status} />
                      <span className="break-all text-sm font-mono text-muted">
                        {mission.mission_id}
                      </span>
                    </div>
                    <h1 className="break-words text-2xl font-bold text-foreground">
                      {mission.title}
                    </h1>
                    <div className="mt-3"><RelationshipLink type="mission" id={mission.id} /></div>
                    <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-muted">
                      {mission.project_id && mission.project_name ? (
                        <Link
                          href={`/projects/${mission.project_id}`}
                          className="text-accent-text underline underline-offset-4"
                        >
                          {mission.project_name}
                        </Link>
                      ) : mission.project_id ? (
                        <Link
                          href={`/projects/${mission.project_id}`}
                          className="text-accent-text underline underline-offset-4"
                        >
                          View Project
                        </Link>
                      ) : (
                        <span className="text-muted">No project</span>
                      )}
                      {createdAt && (
                        <>
                          <span className="text-secondary">&bull;</span>
                          <span>Created {createdAt}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                {/* Tags */}
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  {mission.tags.map((tag) => (
                    <span
                      key={tag}
                      className="max-w-full break-words px-2 py-1 text-xs bg-surface text-secondary rounded"
                    >
                      {tag}
                    </span>
                  ))}
                </div>

                {/* Action Buttons */}
                <div className="mt-6 flex flex-wrap gap-3">
                  {["queued", "in_progress"].includes(mission.status) && <button disabled={acting} className="rounded-lg border border-danger-line px-4 py-2 text-sm text-danger" onClick={() => void handleCancelRun()}>Cancel run</button>}
                  {["completed", "blocked", "cancelled", "validation_failed"].includes(mission.status) && <button disabled={acting} className="rounded-lg border border-line px-4 py-2 text-sm" onClick={() => void handleRerun()}>Re-run</button>}

                  {isDraft && (
                    <button
                      onClick={handleSubmitToDeepSearch}
                      disabled={isSubmitting}
                      className="px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium text-sm"
                    >
                      {isSubmitting ? "Submitting..." : "Submit to DeepSearch"}
                    </button>
                  )}
                  {mission.status === "completed" && (mission.result_report_id || mission.result_markdown) && !promotionResult && mission.result_document_ids.length === 0 && (
                    <button
                      onClick={handlePromoteReport}
                      disabled={isPromoting}
                      className="px-4 py-2 bg-success-surface text-success rounded-lg hover:bg-success-surface disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium text-sm"
                    >
                      {isPromoting ? "Promoting..." : "Promote to Document"}
                    </button>
                  )}
                  {promotionResult && (
                    <Link
                      href={`/documents/${promotionResult.document_id}`}
                      className="px-4 py-2 bg-success-surface text-success rounded-lg hover:bg-success-surface transition-colors font-medium text-sm"
                    >
                      View Promoted Document
                    </Link>
                  )}
                  {!promotionResult && mission.result_document_ids.length > 0 && (
                    <Link
                      href={`/documents/${mission.result_document_ids[0]}`}
                      className="px-4 py-2 bg-success-surface text-success rounded-lg hover:bg-success-surface transition-colors font-medium text-sm"
                    >
                      View Promoted Document
                    </Link>
                  )}
                  {isDraft && (
                  <button
                    onClick={() => setIsEditing(true)}
                    className="px-4 py-2 border border-line-strong text-secondary rounded-lg hover:bg-background transition-colors font-medium text-sm"
                  >
                    Edit Mission
                  </button>
                  )}
                  <button
                    onClick={() => { setActionError(null); setDeleteOpen(true); }}
                    className="px-4 py-2 border border-danger-line text-danger rounded-lg hover:bg-danger-surface transition-colors font-medium text-sm"
                  >
                    Delete
                  </button>
                </div>
              </>
            )}

            {submitError && (
              <p className="mt-3 text-sm text-danger">{submitError}</p>
            )}
            {promotionError && (
              <p className="mt-3 text-sm text-danger">{promotionError}</p>
            )}
            {promotionResult && (
              <p className="mt-3 text-sm text-success">
                {promotionResult.message}
                {promotionResult.chunk_count !== null && ` (${promotionResult.chunk_count} chunks created)`}
              </p>
            )}
          </div>

          <div className="flex flex-wrap gap-3 border-b border-line p-4" role="tablist" aria-label="Mission detail">
            {MISSION_TABS.map((tab, index, tabs) => <button key={tab} id={`mission-tab-${tab}`} role="tab" aria-selected={detailTab === tab} aria-controls={`mission-panel-${tab}`} tabIndex={detailTab === tab ? 0 : -1} onKeyDown={event => {
              if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
                event.preventDefault();
                const next = event.key === "Home" ? tabs[0] : event.key === "End" ? tabs[tabs.length - 1] : tabs[(index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length];
                setDetailTab(next); document.getElementById(`mission-tab-${next}`)?.focus();
              }
            }} onClick={() => setDetailTab(tab)} className={`rounded px-4 py-2 ${detailTab === tab ? "bg-accent text-on-accent" : "border border-line"}`}>{tab === "overview" ? "Run" : tab === "results" ? "Results" : "Evidence"}</button>)}
          </div>
          <div role="tabpanel" id="mission-panel-results" aria-labelledby="mission-tab-results" hidden={detailTab !== "results"}>
          {/* Results Markdown Section */}
          {mission.result_markdown && (
            <Section title="Results">
              <div className="flex justify-end mb-2">
                <button
                  onClick={() => downloadFile(
                    mission.result_markdown!,
                    `${mission.mission_id}-results.md`,
                    "text/markdown"
                  )}
                  className="px-3 py-1.5 text-xs font-medium text-accent-text hover:bg-info-surface rounded transition-colors"
                >
                  Export as .md
                </button>
              </div>
              <div className="bg-background rounded-lg p-4 overflow-x-auto">
                <MarkdownRenderer content={mission.result_markdown} />
              </div>
            </Section>
          )}

          {/* Result Links Section */}
          {(mission.result_document_ids.length > 0 || mission.result_report_id) && (
            <Section title="Result Artifacts">
              <ResultLinks
                documentIds={mission.result_document_ids}
                reportId={mission.result_report_id}
              />
            </Section>
          )}


            {!mission.result_markdown && !mission.result_report_id && !mission.result_document_ids.length && <PageState state="empty" title="No results recorded yet." />}
          </div>
          {detailTab === 'evidence' && <div role="tabpanel" id="mission-panel-evidence" aria-labelledby="mission-tab-evidence" className="px-4"><EvidencePanel projectId={mission.project_id} filters={{ mission_id: mission.id }} /></div>}
          <div role="tabpanel" id="mission-panel-overview" aria-labelledby="mission-tab-overview" hidden={detailTab !== 'overview'}>
          <MissionRunActivity mission={mission} />
          {/* Objective Section */}
          <Section title="Objective">
            <p className="text-secondary whitespace-pre-wrap">
              {mission.objective}
            </p>
          </Section>

          {/* Success Criteria Section */}
          {mission.success_criteria.length > 0 && (
            <Section title="Success Criteria">
              <ul className="space-y-2">
                {mission.success_criteria.map((criterion, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-surface-alt flex-shrink-0" />
                    <span className="text-secondary">{criterion}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {/* Deliverables Section */}
          {mission.deliverables.length > 0 && (
            <Section title="Deliverables">
              <ul className="space-y-2">
                {mission.deliverables.map((deliverable, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-accent flex-shrink-0" />
                    <span className="text-secondary">{deliverable}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {/* Research Phases Section */}
          {hasResearchPhases && (
            <Section title="Research plan">
              <ResearchPhases phases={mission.research_phases} />
            </Section>
          )}

          {/* Error Message Section */}
          {mission.error_message && (
            <Section title="Error">
              <div className="bg-danger-surface border border-danger-line rounded-lg p-4">
                <p className="text-danger">{mission.error_message}</p>
              </div>
            </Section>
          )}

          {/* Contract Preview Panel (T40.4) */}
          {missionId && (
            <div className="p-6 border-b border-line">
              <ContractPreviewPanel missionId={missionId} />
            </div>
          )}

          {/* Execution Timeline & Metadata Section */}
          <Section title="Execution">
            <ExecutionTimeline
              status={mission.status}
              createdAt={mission.created_at}
              queuedAt={mission.queued_at}
              startedAt={mission.started_at}
              completedAt={mission.completed_at}
              reportMetadata={mission.result_protocol?.report_metadata}
            />

            {mission.deepsearch_job_id && (
              <div className="mt-6 pt-6 border-t border-line">
                <h3 className="text-sm font-semibold text-secondary uppercase tracking-wide mb-3">
                  Job Details
                </h3>
                <div className="grid gap-4 sm:grid-cols-2 text-sm">
                  <div>
                    <p className="text-muted">DeepSearch Job ID</p>
                    <p className="font-mono text-foreground break-all">
                      {mission.deepsearch_job_id}
                    </p>
                  </div>
                  {mission.created_by && (
                    <div>
                      <p className="text-muted">Created By</p>
                      <p className="text-foreground">{mission.created_by}</p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </Section>


          </div>
        </div>
      </div>
    </div>
  );
}

const MISSION_TABS = ["overview", "results", "evidence"] as const;
type MissionTab = (typeof MISSION_TABS)[number];

export default function MissionDetailPage() {
  return (
    <AuthGate>
      <MissionDetailContent />
    </AuthGate>
  );
}
