/**
 * Project detail page - view/edit project, manage documents
 */

import { AuthGate } from "@/components/AuthGate";
import { documentsApi } from "@/lib/api/documents";
import { projectsApi, type ProjectStats } from "@/lib/api/projects";
import type { Document, Project } from "@/types/document";
import type { PaginatedResponse } from "@/types/pagination";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";

const RESEARCH_TYPES = ["strategic", "tactical", "generative", "evaluative"] as const;
const PAGE_SIZE = 10;

export default function ProjectDetailPage() {
  const router = useRouter();
  const { id } = router.query;
  const projectId = typeof id === "string" ? id : "";

  // Project data
  const { data: project, mutate: mutateProject, isLoading: projectLoading } = useSWR<Project>(
    projectId ? ["project", projectId] : null,
    () => projectsApi.getProject(projectId)
  );

  // Project stats
  const { data: stats, mutate: mutateStats } = useSWR<ProjectStats>(
    projectId ? ["project-stats", projectId] : null,
    () => projectsApi.getProjectStats(projectId)
  );

  // Documents for this project
  const [docPage, setDocPage] = useState(1);
  const { data: documentsResponse, mutate: mutateDocuments, isLoading: docsLoading } = useSWR<PaginatedResponse<Document>>(
    projectId ? ["documents", projectId, "", "", docPage] : null,
    () => documentsApi.listDocuments({ projectId, page: docPage, pageSize: PAGE_SIZE })
  );
  const documents = documentsResponse?.data ?? [];
  const docPagination = documentsResponse?.pagination;

  // Edit mode
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ name: "", description: "", research_type: "" });
  const [saving, setSaving] = useState(false);

  // Upload state
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<string[]>([]);
  const [autoProcess, setAutoProcess] = useState(true);

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
        description: editForm.description || undefined,
        research_type: editForm.research_type || undefined,
      });
      await mutateProject();
      // Invalidate project list caches
      globalMutate((key) => Array.isArray(key) && key[0] === "projects", undefined, { revalidate: true });
      setEditing(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save";
      alert(message);
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
      alert(message);
      setDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  const handleDeleteDocument = async (documentId: string) => {
    if (!confirm("Delete this document?")) return;

    try {
      await documentsApi.deleteDocument(documentId);
      await mutateDocuments();
      await mutateStats();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete";
      alert(message);
    }
  };

  // Upload handlers
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files) {
      setFiles((prev) => [...prev, ...Array.from(e.dataTransfer.files)]);
    }
  };

  const handleUpload = async () => {
    if (!projectId || files.length === 0) return;

    setUploading(true);
    setUploadProgress([]);

    try {
      for (const file of files) {
        setUploadProgress((prev) => [...prev, `Uploading ${file.name}...`]);
        const result = await documentsApi.uploadDocument(projectId, file);

        if (autoProcess) {
          setUploadProgress((prev) => [...prev, `Processing ${file.name}...`]);
          await documentsApi.processDocument(result.id);
          setUploadProgress((prev) => [...prev, `${file.name} complete`]);
        } else {
          setUploadProgress((prev) => [...prev, `${file.name} uploaded`]);
        }
      }

      // Clear files and refresh document list
      setFiles([]);
      await mutateDocuments();
      await mutateStats();
      // Also invalidate the global documents cache
      globalMutate((key) => Array.isArray(key) && key[0] === "documents", undefined, { revalidate: true });

      setTimeout(() => setUploadProgress([]), 3000);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Upload failed";
      setUploadProgress((prev) => [...prev, `Error: ${message}`]);
    } finally {
      setUploading(false);
    }
  };

  if (!projectId) {
    return null;
  }

  if (projectLoading) {
    return (
      <AuthGate>
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
          <p className="text-gray-500">Loading project...</p>
        </div>
      </AuthGate>
    );
  }

  if (!project) {
    return (
      <AuthGate>
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
          <div className="text-center">
            <p className="text-gray-500 mb-4">Project not found</p>
            <Link href="/projects" className="text-blue-600 hover:text-blue-700">
              Back to Projects
            </Link>
          </div>
        </div>
      </AuthGate>
    );
  }

  return (
    <AuthGate>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Breadcrumb */}
          <nav className="mb-6">
            <Link href="/projects" className="text-blue-600 dark:text-blue-400 hover:underline">
              Projects
            </Link>
            <span className="mx-2 text-gray-400">/</span>
            <span className="text-gray-600 dark:text-gray-300">{project.name}</span>
          </nav>

          {/* Project Header */}
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-6 mb-6">
            {editing ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">Name *</label>
                  <input
                    type="text"
                    value={editForm.name}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, name: e.target.value }))}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">Description</label>
                  <textarea
                    value={editForm.description}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, description: e.target.value }))}
                    rows={3}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">Research Type</label>
                  <select
                    value={editForm.research_type}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, research_type: e.target.value }))}
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
                <div className="flex gap-3">
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400"
                  >
                    {saving ? "Saving..." : "Save Changes"}
                  </button>
                  <button
                    onClick={cancelEditing}
                    disabled={saving}
                    className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <div className="flex items-start justify-between">
                  <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{project.name}</h1>
                    {project.description && (
                      <p className="mt-2 text-gray-600 dark:text-gray-400">{project.description}</p>
                    )}
                    <div className="mt-4 flex flex-wrap gap-4 text-sm text-gray-500 dark:text-gray-400">
                      <span>Research Type: {project.research_type || "Not set"}</span>
                      <span>Status: {project.status || "active"}</span>
                      {project.created_at && (
                        <span>Created {formatDistanceToNow(new Date(project.created_at), { addSuffix: true })}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={startEditing}
                      className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => setShowDeleteConfirm(true)}
                      className="px-4 py-2 text-sm text-red-600 border border-red-300 dark:border-red-600 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                {/* Stats */}
                {stats && (
                  <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <StatCard label="Documents" value={stats.document_count} />
                    <StatCard label="Chunks" value={stats.chunk_count} />
                    <StatCard label="Reports" value={stats.report_count} />
                    <StatCard label="Tokens" value={stats.total_tokens.toLocaleString()} />
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Delete Confirmation Modal */}
          {showDeleteConfirm && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
              <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Delete Project?</h3>
                <p className="text-gray-600 dark:text-gray-400 mb-4">
                  This will permanently delete <strong>{project.name}</strong> and all its documents, chunks, and associated data. This action cannot be undone.
                </p>
                <div className="flex gap-3 justify-end">
                  <button
                    onClick={() => setShowDeleteConfirm(false)}
                    disabled={deleting}
                    className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleDelete}
                    disabled={deleting}
                    className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:bg-gray-400"
                  >
                    {deleting ? "Deleting..." : "Delete Project"}
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-3">
            {/* Documents List */}
            <section className="lg:col-span-2 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Documents</h2>
              </div>

              {docsLoading && !documentsResponse ? (
                <p className="text-gray-500">Loading documents...</p>
              ) : documents.length === 0 ? (
                <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-8 text-center">
                  <p className="text-gray-500 dark:text-gray-400">No documents yet. Upload some using the panel on the right.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {documents.map((doc) => (
                    <div
                      key={doc.id}
                      className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1 min-w-0">
                          <Link
                            href={`/documents/${doc.id}`}
                            className="font-medium text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400 truncate block"
                          >
                            {doc.name}
                          </Link>
                          <div className="mt-1 flex flex-wrap gap-3 text-xs text-gray-500 dark:text-gray-400">
                            <span>{doc.file_type || doc.mime_type?.split("/")[1] || "Unknown"}</span>
                            {doc.file_size && <span>{(doc.file_size / 1024).toFixed(1)} KB</span>}
                            {doc.uploaded_at && (
                              <span>{formatDistanceToNow(new Date(doc.uploaded_at), { addSuffix: true })}</span>
                            )}
                          </div>
                          <div className="mt-2 flex gap-2">
                            <StatusBadge label="Processed" status={doc.processed} />
                            <StatusBadge label="Chunked" status={doc.chunked} />
                            <StatusBadge label="Embedded" status={doc.embedded} />
                          </div>
                        </div>
                        <button
                          onClick={() => handleDeleteDocument(doc.id)}
                          className="ml-4 text-sm text-red-600 dark:text-red-400 hover:text-red-700"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}

                  {/* Pagination */}
                  {docPagination && docPagination.pages > 1 && (
                    <div className="flex items-center justify-between pt-2 text-sm">
                      <span className="text-gray-500">
                        Page {docPagination.page} of {docPagination.pages}
                      </span>
                      <div className="flex gap-2">
                        <button
                          onClick={() => setDocPage((p) => Math.max(1, p - 1))}
                          disabled={docPage === 1}
                          className="px-3 py-1 border border-gray-300 dark:border-gray-600 rounded disabled:opacity-40"
                        >
                          Prev
                        </button>
                        <button
                          onClick={() => setDocPage((p) => Math.min(docPagination.pages, p + 1))}
                          disabled={docPage >= docPagination.pages}
                          className="px-3 py-1 border border-gray-300 dark:border-gray-600 rounded disabled:opacity-40"
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </section>

            {/* Upload Panel */}
            <aside className="space-y-4">
              <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-6">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Upload Documents</h3>

                {/* Drop Zone */}
                <div
                  className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-6 text-center hover:border-blue-500 dark:hover:border-blue-400 transition-colors cursor-pointer"
                  onDrop={handleDrop}
                  onDragOver={(e) => e.preventDefault()}
                  onClick={() => document.getElementById("file-input-detail")?.click()}
                >
                  <input
                    id="file-input-detail"
                    type="file"
                    multiple
                    accept=".pdf,.docx,.pptx,.csv,.xlsx,.md,.txt"
                    onChange={handleFileSelect}
                    className="hidden"
                    disabled={uploading}
                  />

                  {files.length === 0 ? (
                    <>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        Drop files here or click to select
                      </p>
                      <p className="mt-1 text-xs text-gray-400">
                        PDF, DOCX, PPTX, CSV, XLSX, MD, TXT
                      </p>
                    </>
                  ) : (
                    <div className="text-left">
                      <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                        {files.length} file(s) selected:
                      </p>
                      <ul className="space-y-1">
                        {files.map((file, idx) => (
                          <li key={idx} className="text-sm flex justify-between items-center">
                            <span className="truncate text-gray-900 dark:text-white">{file.name}</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setFiles(files.filter((_, i) => i !== idx));
                              }}
                              className="text-red-600 text-xs ml-2"
                              disabled={uploading}
                            >
                              Remove
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                {/* Auto-process option */}
                <label className="flex items-center gap-2 mt-4 text-sm text-gray-700 dark:text-gray-300">
                  <input
                    type="checkbox"
                    checked={autoProcess}
                    onChange={(e) => setAutoProcess(e.target.checked)}
                    className="rounded"
                    disabled={uploading}
                  />
                  Auto-process after upload
                </label>

                {/* Progress */}
                {uploadProgress.length > 0 && (
                  <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-900 rounded border text-sm max-h-32 overflow-y-auto">
                    {uploadProgress.map((msg, idx) => (
                      <div key={idx} className="text-gray-700 dark:text-gray-300">{msg}</div>
                    ))}
                  </div>
                )}

                {/* Upload Button */}
                <button
                  onClick={handleUpload}
                  disabled={uploading || files.length === 0}
                  className="w-full mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                >
                  {uploading ? "Uploading..." : "Upload"}
                </button>
              </div>
            </aside>
          </div>
        </div>
      </div>
    </AuthGate>
  );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3 text-center">
      <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
    </div>
  );
}

function StatusBadge({ label, status }: { label: string; status: boolean }) {
  return (
    <span
      className={`px-2 py-0.5 text-xs rounded ${
        status
          ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
          : "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400"
      }`}
    >
      {status ? "✓" : "○"} {label}
    </span>
  );
}
