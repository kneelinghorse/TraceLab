import type { Telemetry } from '../telemetry/telemetry.js';

export class IngestionMetrics {
  private readonly processedDocumentsCounter;
  private readonly processedChunksCounter;
  private readonly failedDocumentsCounter;
  private readonly deletedDocumentsCounter;
  private readonly processingDuration;

  constructor(telemetry: Telemetry) {
    this.processedDocumentsCounter = telemetry.counter('markdown_documents_processed', {
      description: 'Number of Markdown documents successfully ingested',
    });
    this.processedChunksCounter = telemetry.counter('markdown_chunks_processed', {
      description: 'Number of Markdown chunks embedded and stored',
    });
    this.failedDocumentsCounter = telemetry.counter('markdown_documents_failed', {
      description: 'Number of Markdown documents that failed ingestion',
    });
    this.deletedDocumentsCounter = telemetry.counter('markdown_documents_deleted', {
      description: 'Number of Markdown documents deleted via ingestion pipeline',
    });
    this.processingDuration = telemetry.histogram('markdown_ingestion_duration_ms', {
      description: 'Document ingestion duration in milliseconds',
      unit: 'ms',
    });
  }

  recordSuccess(documentId: string, chunkCount: number, durationMs: number): void {
    this.processedDocumentsCounter.add(1, { document_id: documentId });
    this.processedChunksCounter.add(chunkCount, { document_id: documentId });
    this.processingDuration.record(durationMs, { document_id: documentId });
  }

  recordFailure(documentId: string): void {
    this.failedDocumentsCounter.add(1, { document_id: documentId });
  }

  recordDeletion(documentId: string): void {
    this.deletedDocumentsCounter.add(1, { document_id: documentId });
  }
}
