import { PaginationBar } from "@/components/ui/PaginationBar";
import { PageState } from "@/components/ui/PageState";
import { useAuth } from "@/contexts/AuthContext";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { parseApiTimestamp } from "@/lib/api/timestamps";
import { AuthGate } from "@/components/AuthGate";
import { projectsApi } from "@/lib/api/projects";
import type { Project } from "@/types/document";
import type { PaginatedResponse } from "@/types/pagination";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

const PAGE_SIZE = 10;
const RESEARCH_TYPES = ["strategic", "tactical", "generative", "evaluative"] as const;

export default function ProjectsPage() {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [formState, setFormState] = useState({ name: "", description: "", research_type: "" });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const { data: projectResponse, mutate, isLoading, error } = useSWR<PaginatedResponse<Project>>(
    ["projects", user?.user_id, page, search],
    () =>
      projectsApi.listProjects({
        page,
        pageSize: PAGE_SIZE,
        search: search.trim() || undefined,
      }),
  );

  const projects = projectResponse?.data ?? [];
  const pagination = projectResponse?.pagination;
  const totalPages = pagination?.pages ?? 0;


  const handleCreate = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!formState.name.trim()) {
      setFormError("Project name is required.");
      return;
    }

    setSubmitting(true);
    setFormError(null);

    try {
      await projectsApi.createProject({
        name: formState.name.trim(),
        description: formState.description || undefined,
        research_type: formState.research_type || undefined,
      });
      setFormState({ name: "", description: "", research_type: "" });
      mutate();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to create project";
      setFormError(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthGate>
      <div className="min-h-screen bg-background">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <header className="mb-8">
            <h1 className="text-3xl font-bold text-foreground">Projects</h1>
            <p className="mt-2 text-secondary">
              Research bundles bring sources, evidence, context and results together.
            </p>
          </header>

          <div className="space-y-6">
            <details className="panel p-5"><summary className="cursor-pointer font-semibold">Create a project</summary>
            <form onSubmit={handleCreate} className="bg-surface border border-line rounded-lg p-6 space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground">Create Project</h2>
                <p className="text-sm text-muted">Required for document uploads and mission tracking.</p>
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                <div>
                  <label className="block text-sm font-medium text-secondary mb-1">Name *</label>
                  <input
                    type="text"
                    aria-label="Project name"
                    value={formState.name}
                    onChange={(e) => setFormState((prev) => ({ ...prev, name: e.target.value }))}
                    className="w-full px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground"
                    placeholder="E.g., 2025 Field Insights"
                    required
                  />
                </div>
                <div>
                  <label htmlFor="project-research-type" className="block text-sm font-medium text-secondary mb-1">Research Type</label>
                  <select id="project-research-type"
                    value={formState.research_type}
                    onChange={(e) => setFormState((prev) => ({ ...prev, research_type: e.target.value }))}
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
                <div className="flex items-end">
                  <button
                    type="submit"
                    disabled={submitting}
                    className="w-full px-6 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent disabled:bg-surface-alt"
                  >
                    {submitting ? "Creating..." : "Create Project"}
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-secondary mb-1">Description (optional)</label>
                <textarea
                  aria-label="Project description"
                    value={formState.description}
                  onChange={(e) => setFormState((prev) => ({ ...prev, description: e.target.value }))}
                  className="w-full px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground"
                  rows={2}
                  placeholder="Brief description of the project..."
                />
              </div>
              {formError && <p role="alert" className="text-sm text-danger">{formError}</p>}
            </form>
            </details>

            {/* Project List */}
            <div className="bg-surface border border-line rounded-lg p-6 space-y-4">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-foreground">Project library</h2>
                  {pagination && <p className="mt-1 text-sm text-secondary">{pagination.total.toLocaleString()} matching projects</p>}
                  <p className="text-sm text-muted">Click a project to manage documents and settings.</p>
                </div>
                <input
                  type="search"
                  placeholder="Search..."
                  aria-label="Search projects"
                    value={search}
                  onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                  className="px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground"
                />
              </div>

              {error ? <PageState state="error" title="Projects could not load." onRetry={() => void mutate()} /> : isLoading && !projectResponse ? (
                <PageState state="loading" title="Loading projects…" />
              ) : projects.length === 0 ? (
                <PageState state="empty" title="No projects found. Create one to begin." />
              ) : (
                <div className="divide-y divide-line">
                  {projects.map((project) => (
                    <Link
                      key={project.id}
                      href={`/projects/${project.id}`}
                      className="group block py-5"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <p className="break-words font-semibold text-foreground group-hover:text-accent-text">
                            {project.name}
                          </p>
                          {project.description && (
                            <p className="text-sm text-muted mt-1 line-clamp-2">{project.description}</p>
                          )}
                        </div>
                        {project.research_type && (
                          <span className="ml-2 px-2 py-1 text-xs rounded bg-surface text-secondary">
                            {project.research_type}
                          </span>
                        )}
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-muted">
                        <span>
                          {project.updated_at ? `Updated ${formatDistanceToNow(parseApiTimestamp(project.updated_at), { addSuffix: true })}` : "Update time unavailable"}
                        </span>
                        <StatusBadge status={project.status || "unknown"} />
                      </div>
                    </Link>
                  ))}
                </div>
              )}

              <PaginationBar page={pagination?.page ?? page} pages={totalPages} onChange={setPage} />
            </div>
          </div>
        </div>
      </div>
    </AuthGate>
  );
}
