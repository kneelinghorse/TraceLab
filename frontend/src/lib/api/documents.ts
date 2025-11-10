/**
 * Document API client
 */

import type { Document, DocumentProcessResult, DocumentUploadResponse, Project } from "@/types/document";
import { httpClient } from "./http";

export const documentsApi = {
  /**
   * List all projects
   */
  async listProjects(): Promise<Project[]> {
    const response = await httpClient.get("/api/v1/projects");
    return response as Project[];
  },

  /**
   * Get project by ID
   */
  async getProject(projectId: string): Promise<Project> {
    const response = await httpClient.get(`/api/v1/projects/${projectId}`);
    return response as Project;
  },

  /**
   * Create a new project
   */
  async createProject(data: { name: string; description?: string; research_type?: string }): Promise<Project> {
    const response = await httpClient.post("/api/v1/projects", data);
    return response as Project;
  },

  /**
   * List documents in a project
   */
  async listDocuments(projectId?: string): Promise<Document[]> {
    const params = projectId ? { project_id: projectId } : {};
    const response = await httpClient.get("/api/v1/documents", { params });
    return response as Document[];
  },

  /**
   * Get document by ID
   */
  async getDocument(documentId: string): Promise<Document> {
    const response = await httpClient.get(`/api/v1/documents/${documentId}`);
    return response as Document;
  },

  /**
   * Upload a document
   */
  async uploadDocument(projectId: string, file: File): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/api/v1/documents/upload?project_id=${projectId}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${localStorage.getItem("tracelab_token") || ""}`,
      },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Upload failed" }));
      throw new Error(error.detail || "Upload failed");
    }

    return response.json();
  },

  /**
   * Process a document
   */
  async processDocument(documentId: string): Promise<DocumentProcessResult> {
    const response = await httpClient.post(`/api/v1/documents/${documentId}/process`, {});
    return response as DocumentProcessResult;
  },

  /**
   * Delete a document
   */
  async deleteDocument(documentId: string): Promise<void> {
    await httpClient.delete(`/api/v1/documents/${documentId}`);
  },
};

