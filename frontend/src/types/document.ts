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
