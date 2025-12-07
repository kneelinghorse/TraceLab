import { AuthGate } from "@/components/AuthGate";
import { projectsApi } from "@/lib/api/projects";
import type { Project } from "@/types/document";
import type { PaginatedResponse } from "@/types/pagination";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { useEffect, useState } from "react";
import useSWR from "swr";

const PAGE_SIZE = 10;
const RESEARCH_TYPES = ["strategic", "tactical", "generative", "evaluative"] as const;

export default function ProjectsPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [formState, setFormState] = useState({ name: "", description: "", research_type: "" });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

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

  useEffect(() => {
    setPage(1);
  }, [search]);

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
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <header className="mb-8">
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Projects</h1>
            <p className="mt-2 text-gray-600 dark:text-gray-400">
              Create and manage research projects. Click a project to view details and upload documents.
            </p>
          </header>

          <div className="space-y-6">
            {/* Create Form */}
            <form onSubmit={handleCreate} className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-6 space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Create Project</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">Required for document uploads and mission tracking.</p>
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
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
                <div className="flex items-end">
                  <button
                    type="submit"
                    disabled={submitting}
                    className="w-full px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400"
                  >
                    {submitting ? "Creating..." : "Create Project"}
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">Description (optional)</label>
                <textarea
                  value={formState.description}
                  onChange={(e) => setFormState((prev) => ({ ...prev, description: e.target.value }))}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
                  rows={2}
                  placeholder="Brief description of the project..."
                />
              </div>
              {formError && <p className="text-sm text-red-600">{formError}</p>}
            </form>

            {/* Project List */}
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-6 space-y-4">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Project Library</h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Click a project to manage documents and settings.</p>
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
                <div className="grid gap-4 sm:grid-cols-2">
                  {projects.map((project) => (
                    <Link
                      key={project.id}
                      href={`/projects/${project.id}`}
                      className="block border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:border-blue-400 hover:shadow-md transition-all group"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1 min-w-0">
                          <p className="font-semibold text-gray-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400 truncate">
                            {project.name}
                          </p>
                          {project.description && (
                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">{project.description}</p>
                          )}
                        </div>
                        {project.research_type && (
                          <span className="ml-2 px-2 py-1 text-xs rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                            {project.research_type}
                          </span>
                        )}
                      </div>
                      <div className="mt-3 flex items-center gap-4 text-xs text-gray-400">
                        <span>
                          Updated {project.updated_at ? formatDistanceToNow(new Date(project.updated_at), { addSuffix: true }) : "recently"}
                        </span>
                        <span className={`px-2 py-0.5 rounded ${project.status === "active" ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300" : "bg-gray-100 text-gray-600"}`}>
                          {project.status || "active"}
                        </span>
                      </div>
                    </Link>
                  ))}
                </div>
              )}

              <ProjectsPagination page={pagination?.page ?? page} pages={totalPages} onChange={setPage} />
            </div>
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
