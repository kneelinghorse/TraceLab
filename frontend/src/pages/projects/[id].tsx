import { HttpError } from "@/lib/api/http";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PaginationBar } from "@/components/ui/PaginationBar";
import { PageState } from "@/components/ui/PageState";
import { Dialog } from "@/components/ui/Dialog";
import { useFeedback } from "@/components/ui/useFeedback";
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
  const { askConfirmation, notify, feedback } = useFeedback();
  const router = useRouter();
  const { id } = router.query;
  const projectId = typeof id === "string" ? id : "";

  // Project data
  const { data: project, mutate: mutateProject, isLoading: projectLoading, error: projectError } = useSWR<Project>(
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
  const { data: documentsResponse, mutate: mutateDocuments, isLoading: docsLoading, error: docsError } = useSWR<PaginatedResponse<Document>>(
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

  const handleDeleteDocument = async (documentId: string) => {
    if (!await askConfirmation("Delete this document?")) return;

    try {
      await documentsApi.deleteDocument(documentId);
      await mutateDocuments();
      await mutateStats();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete";
      notify(message);
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

  if (projectError instanceof HttpError && projectError.status === 404) return <AuthGate><PageState state="empty" title="Project not found." /></AuthGate>;
  if (projectError) return <AuthGate><PageState state="error" title="Project could not load." onRetry={() => void mutateProject()} /></AuthGate>;

  if (projectLoading) {
    return (
      <AuthGate>
      {feedback}
        <div className="min-h-screen bg-background dark:bg-background flex items-center justify-center">
          <p className="text-muted">Loading project...</p>
        </div>
      </AuthGate>
    );
  }

  if (!project) {
    return (
      <AuthGate>
      {feedback}
        <div className="min-h-screen bg-background dark:bg-background flex items-center justify-center">
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
      <div className="min-h-screen bg-background dark:bg-background">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Breadcrumb */}
          <nav className="mb-6">
            <Link href="/projects" className="text-accent-text dark:text-accent-text underline underline-offset-4">
              Projects
            </Link>
            <span className="mx-2 text-muted">/</span>
            <span className="text-secondary dark:text-secondary">{project.name}</span>
          </nav>

          {/* Project Header */}
          <div className="bg-surface dark:bg-surface border border-line dark:border-line rounded-lg p-6 mb-6">
            {editing ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">Name *</label>
                  <input
                    aria-label="Project name"
                    type="text"
                    value={editForm.name}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, name: e.target.value }))}
                    className="w-full px-4 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-background text-foreground dark:text-foreground"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">Description</label>
                  <textarea
                    aria-label="Project description"
                    value={editForm.description}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, description: e.target.value }))}
                    rows={3}
                    className="w-full px-4 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-background text-foreground dark:text-foreground"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-secondary dark:text-secondary mb-1">Research Type</label>
                  <select
                    aria-label="Research type"
                    value={editForm.research_type}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, research_type: e.target.value }))}
                    className="w-full px-4 py-2 border border-line-strong dark:border-line-strong rounded-lg bg-surface dark:bg-background text-foreground dark:text-foreground"
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
                    className="px-4 py-2 border border-line-strong dark:border-line-strong rounded-lg hover:bg-background dark:hover:bg-surface-alt"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h1 className="text-2xl font-bold text-foreground dark:text-foreground">{project.name}</h1>
                    {project.description && (
                      <p className="mt-2 text-secondary dark:text-muted">{project.description}</p>
                    )}
                    <div className="mt-4 flex flex-wrap gap-4 text-sm text-muted dark:text-muted">
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
                      className="px-4 py-2 text-sm border border-line-strong dark:border-line-strong rounded-lg hover:bg-background dark:hover:bg-surface-alt"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => setShowDeleteConfirm(true)}
                      className="px-4 py-2 text-sm text-danger border border-danger-line dark:border-danger-line rounded-lg hover:bg-danger-surface dark:hover:bg-danger-surface"
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
          <Dialog open={showDeleteConfirm} title="Delete project" onClose={() => { if (!deleting) setShowDeleteConfirm(false); }}>
                <p className="text-secondary dark:text-muted mb-4">
                  This will delete <strong>{project.name}</strong> and all its documents, chunks, and associated data.
                </p>
                <div className="flex gap-3 justify-end">
                  <button
                    onClick={() => setShowDeleteConfirm(false)}
                    disabled={deleting}
                    className="px-4 py-2 border border-line-strong dark:border-line-strong rounded-lg hover:bg-background dark:hover:bg-surface-alt"
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

          <div className="grid gap-6 lg:grid-cols-3">
            {/* Documents List */}
            <section className="lg:col-span-2 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-foreground dark:text-foreground">Documents</h2>
              </div>

              {docsError ? <PageState state="error" title="Documents could not load." onRetry={() => void mutateDocuments()} /> : docsLoading && !documentsResponse ? (
                <p className="text-muted">Loading documents...</p>
              ) : documents.length === 0 ? (
                <div className="bg-surface dark:bg-surface border border-line dark:border-line rounded-lg p-8 text-center">
                  <p className="text-muted dark:text-muted">No documents yet. Upload some using the panel on the right.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {documents.map((doc) => (
                    <div
                      key={doc.id}
                      className="bg-surface dark:bg-surface border border-line dark:border-line rounded-lg p-4"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <Link
                            href={`/documents/${doc.id}`}
                            className="font-medium text-foreground dark:text-foreground hover:text-accent-text dark:hover:text-accent-text truncate block"
                          >
                            {doc.name}
                          </Link>
                          <div className="mt-1 flex flex-wrap gap-3 text-xs text-muted dark:text-muted">
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
                          className="ml-4 text-sm text-danger dark:text-danger hover:text-danger"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}

                  {/* Pagination */}
                  <PaginationBar page={docPage} pages={docPagination?.pages ?? 0} onChange={setDocPage} label="Project document pages" />
                </div>
              )}
            </section>

            {/* Upload Panel */}
            <aside className="space-y-4">
              <div className="bg-surface dark:bg-surface border border-line dark:border-line rounded-lg p-6">
                <h3 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">Upload Documents</h3>

                {/* Drop Zone */}
                <div
                  className="border-2 border-dashed border-line-strong dark:border-line-strong rounded-lg p-6 text-center hover:border-info-line dark:hover:border-info-line transition-colors cursor-pointer"
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
                      <p className="text-sm text-secondary dark:text-muted">
                        Drop files here or click to select
                      </p>
                      <p className="mt-1 text-xs text-muted">
                        PDF, DOCX, PPTX, CSV, XLSX, MD, TXT
                      </p>
                    </>
                  ) : (
                    <div className="text-left">
                      <p className="text-sm text-secondary dark:text-muted mb-2">
                        {files.length} file(s) selected:
                      </p>
                      <ul className="space-y-1">
                        {files.map((file, idx) => (
                          <li key={idx} className="text-sm flex justify-between items-center">
                            <span className="truncate text-foreground dark:text-foreground">{file.name}</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setFiles(files.filter((_, i) => i !== idx));
                              }}
                              className="text-danger text-xs ml-2"
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
                <label className="flex items-center gap-2 mt-4 text-sm text-secondary dark:text-secondary">
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
                  <div className="mt-4 p-3 bg-background dark:bg-background rounded border text-sm max-h-32 overflow-y-auto">
                    {uploadProgress.map((msg, idx) => (
                      <div key={idx} className="text-secondary dark:text-secondary">{msg}</div>
                    ))}
                  </div>
                )}

                {/* Upload Button */}
                <button
                  onClick={handleUpload}
                  disabled={uploading || files.length === 0}
                  className="w-full mt-4 px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent disabled:bg-surface-alt disabled:cursor-not-allowed"
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
    <div className="bg-background dark:bg-background rounded-lg p-3 text-center">
      <p className="text-2xl font-bold text-foreground dark:text-foreground">{value}</p>
      <p className="text-xs text-muted dark:text-muted">{label}</p>
    </div>
  );
}
