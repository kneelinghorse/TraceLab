export type IngestionAction = 'upsert' | 'delete';

export interface IngestionTask {
  eventId: string;
  action: IngestionAction;
  absolutePath: string;
  sourceUri: string;
  projectId?: string;
  documentId: string;
  docType?: string;
  updatedAt: string;
}

export interface MarkdownChunk {
  chunkId: string;
  chunkIndex: number;
  headingTrail: string[];
  content: string;
  textForEmbedding: string;
  chunkHash: string;
}

export interface ChunkPayload extends Record<string, unknown> {
  chunk_id: string;
  document_id: string;
  project_id?: string;
  source_uri: string;
  chunk_index: number;
  heading_trail: string[];
  doc_type?: string;
  content: string;
  chunk_hash: string;
  content_type: 'markdown';
  created_at: string;
  updated_at: string;
  front_matter?: Record<string, unknown>;
}

export interface IngestionMetricsSnapshot {
  processedDocuments: number;
  processedChunks: number;
  failedDocuments: number;
  deletedDocuments: number;
}
