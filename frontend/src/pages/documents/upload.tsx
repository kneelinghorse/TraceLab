/**
 * Document upload page
 */

import { AuthGate } from "@/components/AuthGate";
import { documentsApi } from "@/lib/api/documents";
import { projectsApi } from "@/lib/api/projects";
import type { Project } from "@/types/document";
import type { PaginatedResponse } from "@/types/pagination";
import { useRouter } from "next/router";
import { useState } from "react";
import useSWR from "swr";

export default function DocumentUploadPage() {
  const router = useRouter();
  const [selectedProject, setSelectedProject] = useState<string>("");
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<string[]>([]);
  const [autoProcess, setAutoProcess] = useState(true);

  const { data: projectResponse } = useSWR<PaginatedResponse<Project>>(
    ["projects", "upload"],
    () => projectsApi.listProjects({ pageSize: 100 })
  );
  const projects = projectResponse?.data ?? [];

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles(Array.from(e.target.files));
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files) {
      setFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleUpload = async () => {
    if (!selectedProject) {
      alert("Please select a project");
      return;
    }

    if (files.length === 0) {
      alert("Please select files to upload");
      return;
    }

    setUploading(true);
    setProgress([]);

    try {
      for (const file of files) {
        setProgress((prev) => [...prev, `Uploading ${file.name}...`]);
        const result = await documentsApi.uploadDocument(selectedProject, file);

        if (autoProcess) {
          setProgress((prev) => [...prev, `Processing ${file.name}...`]);
          await documentsApi.processDocument(result.id);
          setProgress((prev) => [...prev, `✓ ${file.name} complete`]);
        } else {
          setProgress((prev) => [...prev, `✓ ${file.name} uploaded`]);
        }
      }

      // Success - redirect to documents list
      setTimeout(() => {
        router.push("/documents");
      }, 1000);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Upload failed";
      setProgress((prev) => [...prev, `✗ Error: ${message}`]);
    } finally {
      setUploading(false);
    }
  };

  return (
    <AuthGate>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Upload Documents</h1>
            <p className="mt-2 text-gray-600 dark:text-gray-400">
              Upload research documents to your project
            </p>
          </div>

          {/* Upload Form */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-8">
            {/* Project Selection */}
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">
                Select Project *
              </label>
              <select
                value={selectedProject}
                onChange={(e) => setSelectedProject(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
                disabled={uploading}
              >
                <option value="">Choose a project...</option>
                {projects?.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </div>

            {/* File Drop Zone */}
            <div
              className="mb-6 border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-lg p-12 text-center hover:border-blue-500 dark:hover:border-blue-400 transition-colors cursor-pointer"
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onClick={() => document.getElementById("file-input")?.click()}
            >
              <input
                id="file-input"
                type="file"
                multiple
                accept=".pdf,.docx,.pptx,.csv,.xlsx,.md,.txt"
                onChange={handleFileSelect}
                className="hidden"
                disabled={uploading}
              />

              {files.length === 0 ? (
                <>
                  <svg
                    className="mx-auto h-12 w-12 text-gray-400"
                    stroke="currentColor"
                    fill="none"
                    viewBox="0 0 48 48"
                  >
                    <path
                      d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                    Drag and drop files here, or click to select files
                  </p>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-500">
                    Supported: PDF, DOCX, PPTX, CSV, XLSX, MD, TXT
                  </p>
                </>
              ) : (
                <div>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                    {files.length} file(s) selected:
                  </p>
                  <ul className="text-left max-w-md mx-auto">
                    {files.map((file, idx) => (
                      <li key={idx} className="text-sm text-gray-900 dark:text-white py-1 flex justify-between items-center">
                        <span>{file.name}</span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setFiles(files.filter((_, i) => i !== idx));
                          }}
                          className="text-red-600 hover:text-red-700 text-xs"
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

            {/* Options */}
            <div className="mb-6">
              <label className="flex items-center gap-2 text-sm text-gray-900 dark:text-white">
                <input
                  type="checkbox"
                  checked={autoProcess}
                  onChange={(e) => setAutoProcess(e.target.checked)}
                  className="rounded"
                  disabled={uploading}
                />
                Automatically process documents after upload
              </label>
            </div>

            {/* Progress */}
            {progress.length > 0 && (
              <div className="mb-6 p-4 bg-gray-50 dark:bg-gray-900 rounded border border-gray-200 dark:border-gray-700 max-h-48 overflow-y-auto">
                {progress.map((msg, idx) => (
                  <div key={idx} className="text-sm text-gray-900 dark:text-white py-1">
                    {msg}
                  </div>
                ))}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-4">
              <button
                onClick={handleUpload}
                disabled={uploading || !selectedProject || files.length === 0}
                className="flex-1 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
              >
                {uploading ? "Uploading..." : "Upload Documents"}
              </button>
              <button
                onClick={() => router.push("/documents")}
                disabled={uploading}
                className="px-6 py-3 border border-gray-300 dark:border-gray-700 text-gray-900 dark:text-white rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      </div>
    </AuthGate>
  );
}
