/**
 * Collections API client
 */

import { buildApiUrl, httpClient } from "./http";
import { getStoredAuth } from "@/lib/auth/storage";

export type Collection = {
  id: string;
  name: string;
  description: string | null;
  instructions?: string | null;
  created_at: string;
  updated_at: string;
  item_count: number;
};

export type CollectionItem = {
  id: string;
  collection_id: string;
  chunk_id: string;
  notes: string | null;
  added_at: string;
  chunk_content: string | null;
  document_id: string | null;
};

export type CollectionDetail = Collection & {
  items: CollectionItem[];
};

export type CollectionListResponse = {
  data: Collection[];
  total: number;
};

export type CreateCollectionParams = {
  name: string;
  description?: string | null;
  instructions?: string | null;
};

export type UpdateCollectionParams = {
  name?: string;
  description?: string | null;
  instructions?: string | null;
};

export type AddChunkParams = {
  chunk_id: string;
  notes?: string;
};

export type CollectionDocument = {
  id: string; name: string; project_id: string; file_type: string | null;
  processed: boolean | null; chunked: boolean | null; embedded: boolean | null;
};
export type CollectionDocumentPage = { items: CollectionDocument[]; total: number; page: number; page_size: number };
export type CollectionMissionSeed = {
  collection_id: string; title: string; project_id: string | null; background: string;
  references: { title: string; document_id: string; href: string }[];
  context: Record<string, unknown>;
};

export const collectionsApi = {
  documents(collectionId: string, page = 1, pageSize = 20): Promise<CollectionDocumentPage> {
    return httpClient.get(`/collections/${collectionId}/documents`, { params: { page, page_size: pageSize } });
  },
  addDocument(collectionId: string, documentId: string): Promise<CollectionDocument> {
    return httpClient.post(`/collections/${collectionId}/documents`, { document_id: documentId });
  },
  removeDocument(collectionId: string, documentId: string): Promise<void> {
    return httpClient.delete(`/collections/${collectionId}/documents/${documentId}`);
  },
  missionSeed(collectionId: string): Promise<CollectionMissionSeed> {
    return httpClient.get(`/collections/${collectionId}/mission-seed`);
  },

  /**
   * List all collections
   */
  async list(params?: { project_id?: string; page?: number; page_size?: number }): Promise<CollectionListResponse> {
    return httpClient.get("/collections", { params });
  },

  /**
   * Create a new collection
   */
  async create(params: CreateCollectionParams): Promise<Collection> {
    return httpClient.post("/collections", params);
  },

  /**
   * Get a collection with its items
   */
  async get(collectionId: string): Promise<CollectionDetail> {
    return httpClient.get(`/collections/${collectionId}`);
  },

  /**
   * Update a collection
   */
  async update(collectionId: string, params: UpdateCollectionParams): Promise<Collection> {
    return httpClient.put(`/collections/${collectionId}`, params);
  },

  /**
   * Delete a collection
   */
  async delete(collectionId: string): Promise<void> {
    return httpClient.delete(`/collections/${collectionId}`);
  },

  /**
   * Add a chunk to a collection
   */
  async addChunk(collectionId: string, params: AddChunkParams): Promise<CollectionItem> {
    return httpClient.post(`/collections/${collectionId}/chunks`, params);
  },

  /**
   * Remove a chunk from a collection
   */
  async removeChunk(collectionId: string, chunkId: string): Promise<void> {
    return httpClient.delete(`/collections/${collectionId}/chunks/${chunkId}`);
  },

  /**
   * Export collection as markdown bundle for agent synthesis.
   * Triggers a file download.
   */
  async exportMarkdown(collectionId: string): Promise<void> {
    const auth = getStoredAuth();
    const url = buildApiUrl(`/collections/${collectionId}/export`);

    const response = await fetch(url, {
      method: "GET",
      headers: {
        Authorization: auth?.token ? `Bearer ${auth.token}` : "",
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Export failed" }));
      throw new Error(error.detail || "Export failed");
    }

    // Get filename from Content-Disposition header or use default
    const contentDisposition = response.headers.get("Content-Disposition");
    let filename = "collection-export.md";
    if (contentDisposition) {
      const match = contentDisposition.match(/filename="(.+)"/);
      if (match) {
        filename = match[1];
      }
    }

    // Trigger download
    const blob = await response.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(downloadUrl);
  },
};
