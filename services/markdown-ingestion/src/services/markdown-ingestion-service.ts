import { existsSync } from 'fs';
import { performance } from 'perf_hooks';
import { v5 as uuidv5 } from 'uuid';

import type { AppConfig } from '../config.js';
import type { Logger } from '../logger.js';
import type { IngestionTask } from '../types.js';
import { parseMarkdownFile } from '../markdown/parser.js';
import { chunkMarkdown } from '../markdown/chunker.js';
import { EmbeddingService } from './embedding-service.js';
import { QdrantIngestionClient } from './qdrant-service.js';
import { IngestionMetrics } from './metrics.js';

export class MarkdownIngestionService {
  constructor(
    private readonly config: AppConfig,
    private readonly logger: Logger,
    private readonly embeddings: EmbeddingService,
    private readonly qdrant: QdrantIngestionClient,
    private readonly metrics: IngestionMetrics,
  ) {}

  async handle(task: IngestionTask): Promise<void> {
    if (task.action === 'delete') {
      await this.handleDelete(task);
      return;
    }

    await this.handleUpsert(task);
  }

  private async handleDelete(task: IngestionTask): Promise<void> {
    await this.qdrant.deleteDocument(task.documentId);
    this.metrics.recordDeletion(task.documentId);
    this.logger.info({ documentId: task.documentId }, 'processed delete event');
  }

  private async handleUpsert(task: IngestionTask): Promise<void> {
    const startTime = performance.now();
    if (!existsSync(task.absolutePath)) {
      this.logger.warn({ path: task.absolutePath }, 'skipping ingestion; file no longer exists');
      return;
    }

    try {
      const { content, frontMatter } = await parseMarkdownFile(task.absolutePath);
      const chunks = chunkMarkdown(content, {
        minCharacters: this.config.chunkMinTokens,
        maxCharacters: this.config.chunkMaxTokens,
        overlapCharacters: this.config.chunkOverlap,
      });

      if (chunks.length === 0) {
        this.logger.warn({ documentId: task.documentId }, 'no eligible markdown chunks produced; skipping upsert');
        return;
      }

      const frontMatterDocType =
        typeof frontMatter['doc_type'] === 'string' ? (frontMatter['doc_type'] as string) : undefined;
      const frontMatterProjectId =
        typeof frontMatter['project_id'] === 'string' ? (frontMatter['project_id'] as string) : undefined;
      const docTypeCandidate = task.docType ?? frontMatterDocType ?? this.config.defaultDocType;
      const docType = docTypeCandidate?.trim() ?? this.config.defaultDocType;
      const frontMatterPayload = Object.keys(frontMatter).length > 0 ? frontMatter : undefined;
      const projectIdCandidate = task.projectId ?? frontMatterProjectId ?? this.config.projectId;
      const projectId = projectIdCandidate?.trim();

      const embeddings = await this.embeddings.embedTexts(
        chunks.map((chunk) => chunk.textForEmbedding),
        this.config.openaiEmbeddingModel,
      );

      if (embeddings.length !== chunks.length) {
        throw new Error(
          `Embedding service returned ${embeddings.length} vectors for ${chunks.length} chunks`,
        );
      }

      const points = chunks.map((chunk, index) => {
        const chunkId = uuidv5(`${task.documentId}:${chunk.chunkHash}:${index}`, this.config.documentNamespace);
        return {
          id: chunkId,
          vector: embeddings[index],
          payload: {
            chunk_id: chunkId,
            document_id: task.documentId,
            project_id: projectId,
            source_uri: task.sourceUri,
            chunk_index: chunk.chunkIndex,
            heading_trail: chunk.headingTrail,
            doc_type: docType,
            content: chunk.content,
            chunk_hash: chunk.chunkHash,
            content_type: 'markdown' as const,
            created_at: task.updatedAt,
            updated_at: task.updatedAt,
            front_matter: frontMatterPayload,
          },
        };
      });

      await this.qdrant.upsert(points);

      const durationMs = performance.now() - startTime;
      this.metrics.recordSuccess(task.documentId, chunks.length, durationMs);
      this.logger.info(
        {
          documentId: task.documentId,
          chunkCount: chunks.length,
          durationMs: Math.round(durationMs),
        },
        'ingested markdown document',
      );
    } catch (error) {
      this.metrics.recordFailure(task.documentId);
      this.logger.error({ error, documentId: task.documentId }, 'failed to ingest markdown document');
      throw error;
    }
  }
}
