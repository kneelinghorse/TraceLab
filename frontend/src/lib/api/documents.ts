/**
 * Document API client
 */

import type { Document, DocumentChunk, DocumentProcessResult, DocumentUploadResponse } from "@/types/document";
import type { PaginatedResponse } from "@/types/pagination";
import { buildApiUrl, httpClient } from "./http";
import { getStoredAuth } from "@/lib/auth/storage";

export type ListDocumentsParams = {
  projectId?: string;
  processed?: boolean;
  search?: string;
  page?: number;
  pageSize?: number;
};

export const documentsApi = {
  /**
   * List documents in a project
   */
  async listDocuments(params: ListDocumentsParams = {}): Promise<PaginatedResponse<Document>> {
    const query = {
      project_id: params.projectId,
      processed: params.processed,
      search: params.search,
      page: params.page,
      page_size: params.pageSize,
    };
    return httpClient.get("/documents", { params: query });
  },

  /**
   * Get document by ID
   */
  async getDocument(documentId: string): Promise<Document> {
    const response = await httpClient.get(`/documents/${documentId}`);
    return response as Document;
  },

  /**
   * Upload a document
   */
  async uploadDocument(projectId: string, file: File): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append("file", file);

    const auth = getStoredAuth();
    const token = auth?.token ?? "";
    const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};
    const response = await fetch(buildApiUrl("/documents/upload", { project_id: projectId }), {
      method: "POST",
      headers,
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
    const response = await httpClient.post(`/documents/${documentId}/process`, {});
    return response as DocumentProcessResult;
  },

  /**
   * Delete a document
   */
  async deleteDocument(documentId: string): Promise<void> {
    await httpClient.delete(`/documents/${documentId}`);
  },

  /**
   * List chunks for a document
   */
  async listChunks(
    documentId: string,
    params: { page?: number; pageSize?: number } = {}
  ): Promise<PaginatedResponse<DocumentChunk>> {
    const query = {
      page: params.page,
      page_size: params.pageSize,
    };
    return httpClient.get(`/documents/${documentId}/chunks`, { params: query });
  },
};
