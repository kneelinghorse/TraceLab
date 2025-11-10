/**
 * Documents list page
 */

import { AuthGate } from "@/components/AuthGate";
import { documentsApi } from "@/lib/api/documents";
import type { Document, Project } from "@/types/document";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

export default function DocumentsPage() {
  const [selectedProject, setSelectedProject] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const { data: projects } = useSWR<Project[]>("projects", () => documentsApi.listProjects());
  const { data: documents, mutate } = useSWR<Document[]>(
    ["documents", selectedProject],
    () => documentsApi.listDocuments(selectedProject || undefined)
  );

  // Filter documents by status
  const filteredDocuments = documents?.filter((doc) => {
    if (statusFilter === "all") return true;
    if (statusFilter === "processed") return doc.processed;
    if (statusFilter === "processing") return !doc.processed;
    return true;
  });

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
          <div className="mb-6 flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
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
            </div>

            <Link
              href="/documents/upload"
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Upload Document
            </Link>
          </div>

          {/* Documents List */}
          {!filteredDocuments ? (
            <div className="text-center py-12">
              <p className="text-gray-500">Loading documents...</p>
            </div>
          ) : filteredDocuments.length === 0 ? (
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
              {filteredDocuments.map((document) => (
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
            </div>
          )}
        </div>
      </div>
    </AuthGate>
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
