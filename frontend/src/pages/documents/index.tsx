/**
 * Documents list page
 */

import { AuthGate } from "@/components/AuthGate";
import { documentsApi } from "@/lib/api/documents";
import { projectsApi } from "@/lib/api/projects";
import type { Document, Project } from "@/types/document";
import type { PaginatedResponse } from "@/types/pagination";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

const PAGE_SIZE = 10;

export default function DocumentsPage() {
  const [selectedProject, setSelectedProject] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [page, setPage] = useState<number>(1);

  const { data: projectResponse } = useSWR<PaginatedResponse<Project>>(
    ["projects", "selector"],
    () => projectsApi.listProjects({ pageSize: 100 })
  );
  const projects = projectResponse?.data ?? [];

  const { data: documentsResponse, mutate, isLoading } = useSWR<PaginatedResponse<Document>>(
    ["documents", selectedProject, statusFilter, searchTerm, page],
    () =>
      documentsApi.listDocuments({
        projectId: selectedProject || undefined,
        processed: statusFilter === "processed" ? true : statusFilter === "processing" ? false : undefined,
        search: searchTerm || undefined,
        page,
        pageSize: PAGE_SIZE,
      })
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

  useEffect(() => {
    setPage(1);
  }, [selectedProject, statusFilter, searchTerm]);

  const handleDelete = async (documentId: string) => {
    if (!confirm("Are you sure you want to delete this document?")) return;

    try {
      await documentsApi.deleteDocument(documentId);
      mutate();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete document";
      alert(message);
    }
  };

  return (
    <AuthGate>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Documents</h1>
            <p className="mt-2 text-gray-600 dark:text-gray-400">
              Upload and manage your research documents
            </p>
          </div>

          {/* Actions & Filters */}
          <div className="mb-6 flex flex-col lg:flex-row gap-4 items-start lg:items-center justify-between">
            <div className="flex gap-4 items-center flex-wrap">
              {/* Project Filter */}
              <select
                value={selectedProject}
                onChange={(e) => setSelectedProject(e.target.value)}
                className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
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
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
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
                onChange={(e) => setSearchTerm(e.target.value)}
                className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
              />
            </div>

            <Link
              href="/documents/upload"
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Upload Document
            </Link>
          </div>

          {/* Documents List */}
          {isLoading && !documentsResponse ? (
            <div className="text-center py-12">
              <p className="text-gray-500">Loading documents...</p>
            </div>
          ) : documents.length === 0 ? (
            <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
              <p className="text-gray-500 dark:text-gray-400 mb-4">No documents found</p>
              <Link
                href="/documents/upload"
                className="text-blue-600 hover:text-blue-700 dark:text-blue-400"
              >
                Upload your first document →
              </Link>
            </div>
          ) : (
            <div className="grid gap-4">
              {documents.map((document) => (
                <div
                  key={document.id}
                  className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 hover:shadow-lg transition-shadow"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <Link
                        href={`/documents/${document.id}`}
                        className="text-lg font-semibold text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400"
                      >
                        {document.name}
                      </Link>

                      <div className="mt-2 flex flex-wrap gap-4 text-sm text-gray-600 dark:text-gray-400">
                        <span>Project: {projectLookup.get(document.project_id) ?? document.project_id}</span>
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
                        className="px-4 py-2 text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-gray-700 rounded"
                      >
                        View
                      </Link>
                      <button
                        onClick={() => handleDelete(document.id)}
                        className="px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-gray-700 rounded"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
              <PaginationControls
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

type PaginationControlsProps = {
  page: number;
  pages: number;
  onChange: (page: number) => void;
};

function PaginationControls({ page, pages, onChange }: PaginationControlsProps) {
  if (!pages || pages <= 1) {
    return null;
  }

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between pt-4">
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-2 sm:mb-0">
        Page {page} of {pages}
      </p>
      <div className="flex gap-2">
        <button
          onClick={() => onChange(Math.max(1, page - 1))}
          disabled={page === 1}
          className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-lg disabled:opacity-50"
        >
          Previous
        </button>
        <button
          onClick={() => onChange(Math.min(pages, page + 1))}
          disabled={page >= pages}
          className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-lg disabled:opacity-50"
        >
          Next
        </button>
      </div>
    </div>
  );
}

function StatusBadge({ label, status }: { label: string; status: boolean }) {
  return (
    <span
      className={`px-2 py-1 text-xs rounded ${
        status
          ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
          : "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400"
      }`}
    >
      {status ? "✓" : "○"} {label}
    </span>
  );
}
