import { HttpError } from "@/lib/api/http";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PageState } from "@/components/ui/PageState";
import { Dialog } from "@/components/ui/Dialog";
import { useFeedback } from "@/components/ui/useFeedback";
/**
 * Project detail page - view/edit project, manage documents
 */

import { useAuth } from "@/contexts/AuthContext";
import { TabList } from "@/components/ui/TabList";
import { ProjectFavorite } from "@/components/projects/ProjectFavorite";
import { PROJECT_TABS, ProjectResources } from "@/components/projects/ProjectResources";
import { parseApiTimestamp } from "@/lib/api/timestamps";
import { AuthGate } from "@/components/AuthGate";
import { projectsApi, type ProjectStats } from "@/lib/api/projects";
import type { Project } from "@/types/document";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";

const RESEARCH_TYPES = ["strategic", "tactical", "generative", "evaluative"] as const;

export default function ProjectDetailPage() {
  const { query } = useRouter();
  return <ProjectDetail key={typeof query.id === "string" ? query.id : "loading"} />;
}

function ProjectDetail() {
  const { user } = useAuth();
  const { notify, feedback } = useFeedback();
  const router = useRouter();
  const { id } = router.query;
  const projectId = typeof id === "string" ? id : "";

  const tab = PROJECT_TABS.find(value => value === router.query.tab) ?? "Overview";
  const [uploadBusy, setUploadBusy] = useState(false);

  // Project data
  const { data: project, mutate: mutateProject, isLoading: projectLoading, error: projectError } = useSWR<Project>(
    projectId ? ["project", user?.user_id, projectId] : null,
    () => projectsApi.getProject(projectId)
  );

  // Project stats
  const { data: stats, mutate: mutateStats, error: statsError, isLoading: statsLoading } = useSWR<ProjectStats>(
    projectId ? ["project-stats", user?.user_id, projectId] : null,
    () => projectsApi.getProjectStats(projectId)
  );

  // Edit mode
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ name: "", description: "", research_type: "" });
  const [saving, setSaving] = useState(false);

  // Delete state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const startEditing = () => {
    if (project) {
      setEditForm({
        name: project.name,
        description: project.description || "",
        research_type: project.research_type || "",
      });
      setEditing(true);
    }
  };

  const cancelEditing = () => {
    setEditing(false);
    setEditForm({ name: "", description: "", research_type: "" });
  };

  const handleSave = async () => {
    if (!projectId || !editForm.name.trim()) return;

    setSaving(true);
    try {
      await projectsApi.updateProject(projectId, {
        name: editForm.name.trim(),
        description: editForm.description.trim(),
        research_type: editForm.research_type || undefined,
      });
      await mutateProject();
      // Invalidate project list caches
      globalMutate((key) => Array.isArray(key) && key[0] === "projects", undefined, { revalidate: true });
      setEditing(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save";
      notify(message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!projectId) return;

    setDeleting(true);
    try {
      await projectsApi.deleteProject(projectId);
      // Invalidate caches and redirect
      globalMutate((key) => Array.isArray(key) && key[0] === "projects", undefined, { revalidate: true });
      router.push("/projects");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete";
      notify(message);
      setDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  if (!projectId) {
    return null;
  }

  if (projectError instanceof HttpError && projectError.status === 404) return <AuthGate><PageState state="empty" title="Project not found." /></AuthGate>;
  if (projectError) return <AuthGate><PageState state="error" title="Project could not load." onRetry={() => void mutateProject()} /></AuthGate>;

  if (projectLoading) {
    return (
      <AuthGate>
      {feedback}
        <div className="min-h-screen bg-background flex items-center justify-center">
          <p className="text-muted">Loading project...</p>
        </div>
      </AuthGate>
    );
  }

  if (!project) {
    return (
      <AuthGate>
      {feedback}
        <div className="min-h-screen bg-background flex items-center justify-center">
          <div className="text-center">
            <p className="text-muted mb-4">Project not found</p>
            <Link href="/projects" className="text-accent-text hover:text-accent-text">
              Back to Projects
            </Link>
          </div>
        </div>
      </AuthGate>
    );
  }

  return (
    <AuthGate>
      {feedback}
      <div className="min-h-screen bg-background">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Breadcrumb */}
          <nav className="mb-6">
            <Link href="/projects" className="text-accent-text underline underline-offset-4">
              Projects
            </Link>
            <span className="mx-2 text-muted">/</span>
            <span className="text-secondary">{project.name}</span>
          </nav>

          {/* Project Header */}
          <div className="bg-surface border border-line rounded-lg p-6 mb-6">
            {editing ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-secondary mb-1">Name *</label>
                  <input
                    aria-label="Project name"
                    type="text"
                    value={editForm.name}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, name: e.target.value }))}
                    className="w-full px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-secondary mb-1">Description</label>
                  <textarea
                    aria-label="Project description"
                    value={editForm.description}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, description: e.target.value }))}
                    rows={3}
                    className="w-full px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-secondary mb-1">Research Type</label>
                  <select
                    aria-label="Research type"
                    value={editForm.research_type}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, research_type: e.target.value }))}
                    className="w-full px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground"
                  >
                    <option value="">Select...</option>
                    {RESEARCH_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type.charAt(0).toUpperCase() + type.slice(1)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    className="px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent disabled:bg-surface-alt"
                  >
                    {saving ? "Saving..." : "Save Changes"}
                  </button>
                  <button
                    onClick={cancelEditing}
                    disabled={saving}
                    className="px-4 py-2 border border-line-strong rounded-lg hover:bg-background"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h1 className="break-words text-2xl font-bold text-foreground">{project.name}</h1>
                    {project.description && (
                      <p className="mt-2 break-words text-secondary">{project.description}</p>
                    )}
                    <div className="mt-4 flex flex-wrap gap-4 text-sm text-muted">
                      <span>Research Type: {project.research_type || "Not set"}</span>
                      <StatusBadge status={project.status || "unknown"} />
                      {project.created_at && (
                        <span>Created {formatDistanceToNow(parseApiTimestamp(project.created_at), { addSuffix: true })}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <ProjectFavorite projectId={projectId} />
                    <button
                      onClick={startEditing}
                      className="px-4 py-2 text-sm border border-line-strong rounded-lg hover:bg-background"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => setShowDeleteConfirm(true)}
                      className="px-4 py-2 text-sm text-danger border border-danger-line rounded-lg hover:bg-danger-surface"
                    >
                      Delete
                    </button>
                  </div>
                </div>

              </div>
            )}
          </div>

          {/* Delete Confirmation Modal */}
          <Dialog open={showDeleteConfirm} title="Delete project" onClose={() => { if (!deleting) setShowDeleteConfirm(false); }}>
                <p className="text-secondary mb-4">
                  Remove <strong>{project.name}</strong> from active project lists? The project is retained for recovery.
                </p>
                <div className="flex gap-3 justify-end">
                  <button
                    onClick={() => setShowDeleteConfirm(false)}
                    disabled={deleting}
                    className="px-4 py-2 border border-line-strong rounded-lg hover:bg-background"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleDelete}
                    disabled={deleting}
                    className="px-4 py-2 bg-danger-surface text-danger rounded-lg hover:bg-danger-surface disabled:bg-surface-alt"
                  >
                    {deleting ? "Deleting..." : "Delete Project"}
                  </button>
                </div>
          </Dialog>

          <TabList id="project" label="Project sections" tabs={PROJECT_TABS} value={tab} disabled={uploadBusy} onChange={next => void router.replace({ pathname: router.pathname, query: { ...router.query, tab: next } }, undefined, { shallow: true })} />
          <div id="project-panel" role="tabpanel" aria-labelledby={`project-${tab}`} className="mt-6">
            {tab === "Overview" ? <section className="panel space-y-5 p-5">
              <h2 className="text-xl font-semibold">Overview</h2>
              <p className="text-secondary">Sources, context and research outputs in one project.</p>
              {statsError ? <PageState state="error" title="Project totals could not load." onRetry={() => void mutateStats()} /> : statsLoading ? <PageState state="loading" title="Loading project totals…" /> : stats && <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <StatCard label="Documents" value={stats.document_count.toLocaleString()} />
                <StatCard label="Chunks" value={stats.chunk_count.toLocaleString()} />
                <StatCard label="Reports" value={stats.report_count.toLocaleString()} />
                <StatCard label="Tokens" value={stats.total_tokens.toLocaleString()} />
              </div>}
              <div className="flex flex-wrap gap-4 text-sm"><Link className="text-accent-text underline" href={`/projects/${projectId}?tab=Documents`}>Manage documents</Link><Link className="text-accent-text underline" href={`/projects/${projectId}?tab=Missions`}>Inspect missions</Link></div>
              {project.methodology && <p className="break-words text-secondary">Methodology: {project.methodology}</p>}
            </section> : <ProjectResources key={`${projectId}-${tab}`} projectId={projectId} tab={tab} refreshStats={mutateStats} onBusyChange={setUploadBusy} />}
          </div>
        </div>
      </div>
    </AuthGate>
  );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-background rounded-lg p-3 text-center">
      <p className="text-2xl font-bold text-foreground">{value}</p>
      <p className="text-xs text-muted">{label}</p>
    </div>
  );
}
