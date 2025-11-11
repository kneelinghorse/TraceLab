import { AuthGate } from "@/components/AuthGate";
import { projectsApi } from "@/lib/api/projects";
import type { Project } from "@/types/document";
import type { PaginatedResponse } from "@/types/pagination";
import { formatDistanceToNow } from "date-fns";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

const PAGE_SIZE = 10;
const RESEARCH_TYPES = ["strategic", "tactical", "generative", "evaluative"] as const;

export default function ProjectsPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [formState, setFormState] = useState({ name: "", description: "", research_type: "" });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  const { data: projectResponse, mutate, isLoading } = useSWR<PaginatedResponse<Project>>(
    ["projects", page, search],
    () =>
      projectsApi.listProjects({
        page,
        pageSize: PAGE_SIZE,
        search: search ? search.trim() : undefined,
      }),
  );

  const projects = projectResponse?.data ?? [];
  const pagination = projectResponse?.pagination;
  const totalPages = pagination?.pages ?? 0;

  const selectedProject = useMemo(() => {
    if (!selectedProjectId) return null;
    return projects.find((p) => p.id === selectedProjectId) ?? null;
  }, [projects, selectedProjectId]);

  useEffect(() => {
    setPage(1);
  }, [search]);

  useEffect(() => {
    if (selectedProjectId && !projects.some((p) => p.id === selectedProjectId)) {
      setSelectedProjectId(null);
    }
  }, [projects, selectedProjectId]);

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
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <header className="mb-8">
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Projects</h1>
            <p className="mt-2 text-gray-600 dark:text-gray-400">
              Create new initiatives and quickly switch between them during document work.
            </p>
          </header>

          <div className="grid gap-6 lg:grid-cols-3">
            <section className="lg:col-span-2 space-y-6">
              <form onSubmit={handleCreate} className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-6 space-y-4">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Create Project</h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Required for document uploads and mission tracking.</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">Name *</label>
                  <input
                    type="text"
                    value={formState.name}
                    onChange={(e) => setFormState((prev) => ({ ...prev, name: e.target.value }))}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
                    placeholder="E.g., 2025 Field Insights"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">Description</label>
                  <textarea
                    value={formState.description}
                    onChange={(e) => setFormState((prev) => ({ ...prev, description: e.target.value }))}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
                    rows={3}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">Research Type</label>
                  <select
                    value={formState.research_type}
                    onChange={(e) => setFormState((prev) => ({ ...prev, research_type: e.target.value }))}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
                  >
                    <option value="">Select...</option>
                    {RESEARCH_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type.charAt(0).toUpperCase() + type.slice(1)}
                      </option>
                    ))}
                  </select>
                </div>
                {formError && <p className="text-sm text-red-600">{formError}</p>}
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400"
                >
                  {submitting ? "Creating..." : "Create Project"}
                </button>
              </form>

              <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-6 space-y-4">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Project Library</h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Select a project to inspect metadata.</p>
                  </div>
                  <input
                    type="search"
                    placeholder="Search..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
                  />
                </div>

                {isLoading && !projectResponse ? (
                  <p className="text-gray-500">Loading projects...</p>
                ) : projects.length === 0 ? (
                  <p className="text-gray-500">No projects found. Create one to begin.</p>
                ) : (
                  <div className="space-y-3">
                    {projects.map((project) => (
                      <button
                        key={project.id}
                        className={`w-full text-left border rounded-lg p-4 transition-colors ${
                          project.id === selectedProjectId
                            ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                            : "border-gray-200 dark:border-gray-700 hover:border-blue-400"
                        }`}
                        onClick={() => setSelectedProjectId(project.id)}
                      >
                        <p className="font-semibold text-gray-900 dark:text-white">{project.name}</p>
                        {project.description && (
                          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{project.description}</p>
                        )}
                        <p className="text-xs text-gray-400 mt-2">
                          Updated {project.updated_at ? formatDistanceToNow(new Date(project.updated_at), { addSuffix: true }) : "recently"}
                        </p>
                      </button>
                    ))}
                  </div>
                )}

                <ProjectsPagination page={pagination?.page ?? page} pages={totalPages} onChange={setPage} />
              </div>
            </section>

            <aside className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Project Details</h2>
              {selectedProject ? (
                <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">{selectedProject.name}</p>
                    {selectedProject.description && <p className="mt-1">{selectedProject.description}</p>}
                  </div>
                  <div>
                    <span className="font-medium">Research Type:</span> {selectedProject.research_type || "Not set"}
                  </div>
                  <div>
                    <span className="font-medium">Status:</span> {selectedProject.status || "active"}
                  </div>
                  <div>
                    <span className="font-medium">Created:</span>{" "}
                    {selectedProject.created_at ? formatDistanceToNow(new Date(selectedProject.created_at), { addSuffix: true }) : "unknown"}
                  </div>
                  <div>
                    <span className="font-medium">Updated:</span>{" "}
                    {selectedProject.updated_at ? formatDistanceToNow(new Date(selectedProject.updated_at), { addSuffix: true }) : "unknown"}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-gray-500">Select a project to view metadata.</p>
              )}
            </aside>
          </div>
        </div>
      </div>
    </AuthGate>
  );
}

type ProjectsPaginationProps = {
  page: number;
  pages?: number;
  onChange: (page: number) => void;
};

function ProjectsPagination({ page, pages = 0, onChange }: ProjectsPaginationProps) {
  if (!pages || pages <= 1) {
    return null;
  }

  return (
    <div className="flex items-center justify-between pt-4 text-sm text-gray-600 dark:text-gray-400">
      <span>
        Page {page} of {pages}
      </span>
      <div className="flex gap-2">
        <button
          onClick={() => onChange(Math.max(1, page - 1))}
          disabled={page === 1}
          className="px-3 py-1 border border-gray-300 dark:border-gray-700 rounded-lg disabled:opacity-40"
        >
          Previous
        </button>
        <button
          onClick={() => onChange(Math.min(pages, page + 1))}
          disabled={page >= pages}
          className="px-3 py-1 border border-gray-300 dark:border-gray-700 rounded-lg disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  );
}
