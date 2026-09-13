import { StatusBadge } from "@/components/ui/StatusBadge";
import { PaginationBar } from "@/components/ui/PaginationBar";
import { PageState } from "@/components/ui/PageState";
import { useFeedback } from "@/components/ui/useFeedback";
/**
 * Documents list page - cross-project document browser
 */

import { AuthGate } from "@/components/AuthGate";
import { documentsApi } from "@/lib/api/documents";
import { projectsApi } from "@/lib/api/projects";
import type { Document, Project } from "@/types/document";
import type { PaginatedResponse } from "@/types/pagination";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { useMemo, useState } from "react";
import useSWR from "swr";

const PAGE_SIZE = 10;

export default function DocumentsPage() {
  const { askConfirmation, notify, feedback } = useFeedback();
  const [selectedProject, setSelectedProject] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [page, setPage] = useState<number>(1);

  const { data: projectResponse } = useSWR<PaginatedResponse<Project>>(
    ["projects", "selector"],
    () => projectsApi.listProjects({ pageSize: 100 }),
    { revalidateOnMount: true }
  );
  const projects = useMemo(() => projectResponse?.data ?? [], [projectResponse]);

  const { data: documentsResponse, mutate, isLoading, isValidating, error } = useSWR<PaginatedResponse<Document>>(
    ["documents", selectedProject, statusFilter, searchTerm, page],
    () =>
      documentsApi.listDocuments({
        projectId: selectedProject || undefined,
        processed: statusFilter === "processed" ? true : statusFilter === "processing" ? false : undefined,
        search: searchTerm || undefined,
        page,
        pageSize: PAGE_SIZE,
      }),
    { revalidateOnMount: true }
  );

  const documents = documentsResponse?.data ?? [];
  const pagination = documentsResponse?.pagination;
  const totalPages = pagination?.pages ?? 0;
  const resolvedPage = pagination?.page ?? page;

  const projectLookup = useMemo(() => {
    const map = new Map<string, string>();
    projects.forEach((project) => {
      map.set(project.id, project.name);
    });
    return map;
  }, [projects]);


  const handleDelete = async (documentId: string) => {
    if (!await askConfirmation("Are you sure you want to delete this document?")) return;

    try {
      await documentsApi.deleteDocument(documentId);
      mutate();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete document";
      notify(message);
    }
  };

  const handleRefresh = () => {
    mutate();
  };

  return (
    <AuthGate>
      {feedback}
      <div className="min-h-screen bg-background">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-foreground">Documents</h1>
            <p className="mt-2 text-secondary">
              Browse and manage documents across all projects. For project-specific management, use the project detail page.
            </p>
          </div>

          {/* Actions & Filters */}
          <div className="mb-6 flex flex-col lg:flex-row gap-4 items-start lg:items-center justify-between">
            <div className="flex max-w-full gap-4 items-center flex-wrap">
              {/* Project Filter */}
              <select
                value={selectedProject}
                onChange={(e) => { setSelectedProject(e.target.value); setPage(1); }}
                className="px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground"
                aria-label="Filter by project"
              >
                <option value="">All Projects</option>
                {projects?.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>

              {/* Status Filter */}
              <select
                value={statusFilter}
                onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
                className="px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground"
                aria-label="Filter by status"
              >
                <option value="all">All Status</option>
                <option value="processed">Processed</option>
                <option value="processing">Processing</option>
              </select>

              {/* Keyword Filter */}
              <input
                type="search"
                placeholder="Search name..."
                value={searchTerm}
                onChange={(e) => { setSearchTerm(e.target.value); setPage(1); }}
                className="px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground"
                aria-label="Search documents"
              />

              {/* Refresh Button */}
              <button
                type="button"
                onClick={handleRefresh}
                disabled={isValidating}
                className="px-4 py-2 border border-line-strong rounded-lg hover:bg-background disabled:opacity-50"
                title="Refresh documents"
              >
                {isValidating ? (
                  <span className="inline-block w-4 h-4 border-2 border-line-strong border-t-transparent rounded-full animate-spin" />
                ) : (
                  <svg className="w-5 h-5 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                )}
              </button>
            </div>

            <Link
              href="/documents/upload"
              className="px-6 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent transition-colors"
            >
              Upload Document
            </Link>
          </div>

          {/* Documents List */}
          {error ? <PageState state="error" title="Documents could not load." onRetry={() => void mutate()} /> : isLoading && !documentsResponse ? (
            <PageState state="loading" title="Loading documents…" />
          ) : documents.length === 0 ? (
            <div className="text-center py-12 bg-surface rounded-lg border border-line">
              <p className="text-muted mb-4">No documents found</p>
              <Link
                href="/documents/upload"
                className="text-accent-text hover:text-accent-text"
              >
                Upload your first document
              </Link>
            </div>
          ) : (
            <div className="grid gap-4">
              {documents.map((document) => (
                <div
                  key={document.id}
                  className="bg-surface rounded-lg border border-line p-6 hover:shadow-lg transition-shadow"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <Link
                        href={`/documents/${document.id}`}
                        className="text-lg font-semibold text-foreground hover:text-accent-text"
                      >
                        {document.name}
                      </Link>

                      <div className="mt-2 flex flex-wrap gap-4 text-sm text-secondary">
                        <Link
                          href={`/projects/${document.project_id}`}
                          className="hover:text-accent-text"
                        >
                          Project: {projectLookup.get(document.project_id) ?? "Unknown"}
                        </Link>
                        <span>
                          Type: {document.file_type || document.mime_type?.split("/")[1] || "Unknown"}
                        </span>
                        {document.file_size && (
                          <span>
                            Size: {(document.file_size / 1024).toFixed(2)} KB
                          </span>
                        )}
                        {document.uploaded_at && (
                          <span>
                            Uploaded {formatDistanceToNow(new Date(document.uploaded_at), { addSuffix: true })}
                          </span>
                        )}
                      </div>

                      {/* Processing Status */}
                      <div className="mt-3 flex gap-2">
                        <StatusBadge
                          label="Processed"
                          status={document.processed}
                        />
                        <StatusBadge
                          label="Chunked"
                          status={document.chunked}
                        />
                        <StatusBadge
                          label="Embedded"
                          status={document.embedded}
                        />
                      </div>
                    </div>

                    <div className="ml-4 flex gap-2">
                      <Link
                        href={`/documents/${document.id}`}
                        className="px-4 py-2 text-sm text-accent-text hover:bg-info-surface rounded"
                      >
                        View
                      </Link>
                      <button
                        type="button"
                        onClick={() => handleDelete(document.id)}
                        className="px-4 py-2 text-sm text-danger hover:bg-danger-surface rounded"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
              <PaginationBar
                page={resolvedPage}
                pages={totalPages || (documents.length > 0 ? 1 : 0)}
                onChange={setPage}
              />
            </div>
          )}
        </div>
      </div>
    </AuthGate>
  );
}
