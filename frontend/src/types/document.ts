/**
 * Document type definitions
 */

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface Document {
  id: string;
  project_id: string;
  name: string;
  file_path?: string;
  file_type?: string;
  file_size?: number;
  mime_type?: string;
  source_type?: string;
  uploaded_at?: string;
  processed: boolean;
  chunked: boolean;
  embedded: boolean;
  validation_status?: string;
  processing_events?: ProcessingEvent[];

  // Stats computed from chunks
  chunk_count?: number;
  total_tokens?: number;
  word_count?: number;
  preview?: string;
}

export interface ProcessingEvent {
  id: string;
  document_id: string;
  stage: string;
  status: string;
  message?: string;
  details?: Record<string, JsonValue>;
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  research_type?: string;
  methodology?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
  // Owning Space (workspace_id column), surfaced by ProjectRead in T48.3.
  // null/undefined = space-less. Assigned via the admin Spaces page.
  workspace_id?: string | null;
}

export interface DocumentUploadResponse {
  id: string;
  name: string;
  file_size: number;
  mime_type: string;
  processed: boolean;
}

export interface DocumentProcessResult {
  status: string;
  document_id: string;
  stages?: {
    parsing?: string;
    redaction?: string;
    chunking?: string;
    embedding?: string;
  };
  error?: string;
}

export interface DocumentChunk {
  id: string;
  document_id: string;
  chunk_index: number;
  content: string;
  embedding_id?: string;
  token_count?: number;
  start_char?: number;
  end_char?: number;
  prev_chunk_id?: string;
  next_chunk_id?: string;
  created_at: string;
}
