/**
 * Document API client
 */

import type { Document, DocumentChunk, DocumentProcessResult, DocumentUploadResponse } from "@/types/document";
import type { PaginatedResponse } from "@/types/pagination";
import { AUTH_EXPIRED_EVENT, buildApiUrl, HttpError, httpClient } from "./http";
import { clearStoredAuth, getStoredAuth } from "@/lib/auth/storage";

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
  async uploadDocument(projectId: string, file: File, onProgress?: (loaded: number, total: number | null) => void): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append("file", file);

    const auth = getStoredAuth();
    const token = auth?.token ?? "";
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open("POST", buildApiUrl("/documents/upload", { project_id: projectId }));
      if (token) request.setRequestHeader("Authorization", `Bearer ${token}`);
      request.upload.onprogress = event => onProgress?.(event.loaded, event.lengthComputable ? event.total : null);
      request.onerror = () => reject(new Error("Upload connection failed. Check the document list before retrying."));
      request.onabort = () => reject(new Error("Upload interrupted."));
      request.onload = () => {
        if (request.status === 401) {
          clearStoredAuth();
          window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
        }
        let body;
        try { body = JSON.parse(request.responseText); } catch { reject(new HttpError("Upload returned an unreadable response.", request.status)); return; }
        if (request.status < 200 || request.status >= 300) {
          reject(new HttpError(typeof body.detail === "string" ? body.detail : "Upload failed.", request.status));
        } else if (!body.id) {
          reject(new Error("Upload did not return a document ID. Check the document list before retrying."));
        } else { resolve(body); }
      };
      request.send(formData);
    });
  },

  /**
   * Process a document
   */
  async processDocument(documentId: string): Promise<DocumentProcessResult> {
    const response = await httpClient.post(`/documents/${documentId}/process`, {});
    return response as DocumentProcessResult;
  },

  /**
   * Delete a document (soft delete with confirmation)
   */
  async deleteDocument(documentId: string): Promise<void> {
    await httpClient.delete(`/documents/${documentId}`, { params: { confirm: true } });
  },

  /**
   * Download the original document file
   */
  async downloadDocument(documentId: string): Promise<Blob> {
    const auth = getStoredAuth();
    const token = auth?.token ?? "";
    const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};

    const response = await fetch(buildApiUrl(`/documents/${documentId}/download`), {
      method: "GET",
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Download failed" }));
      throw new Error(error.detail || "Download failed");
    }

    return response.blob();
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
