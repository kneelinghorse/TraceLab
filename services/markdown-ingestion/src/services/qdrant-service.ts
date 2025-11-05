import { QdrantClient } from '@qdrant/js-client-rest';

import type { AppConfig } from '../config.js';
import type { Logger } from '../logger.js';
import type { ChunkPayload } from '../types.js';

export interface QdrantPoint {
  id: string;
  vector: number[];
  payload: ChunkPayload;
}

export class QdrantIngestionClient {
  private readonly client: QdrantClient;
  private readonly collection: string;
  private ensuredCollection = false;

  constructor(private readonly config: AppConfig, private readonly logger: Logger) {
    this.client = new QdrantClient({
      url: config.qdrantUrl,
      apiKey: config.qdrantApiKey,
    });
    this.collection = config.qdrantCollection;
  }

  private async ensureCollection(): Promise<void> {
    if (this.ensuredCollection) {
      return;
    }
    const collections = await this.client.getCollections();
    const exists = collections.collections?.some((collection) => collection.name === this.collection);
    if (!exists) {
      await this.client.createCollection(this.collection, {
        vectors: {
          size: this.config.openaiEmbeddingDimension,
          distance: 'Cosine',
        },
        on_disk_payload: true,
      });
      await this.createPayloadIndexes();
      this.logger.info({ collection: this.collection }, 'created qdrant collection for markdown ingestion');
    } else {
      await this.createPayloadIndexes();
    }
    this.ensuredCollection = true;
  }

  private async createPayloadIndexes(): Promise<void> {
    const fields: Array<{ field_name: string; field_schema: 'keyword' | 'integer' }>
      = [
        { field_name: 'project_id', field_schema: 'keyword' },
        { field_name: 'document_id', field_schema: 'keyword' },
        { field_name: 'source_uri', field_schema: 'keyword' },
        { field_name: 'doc_type', field_schema: 'keyword' },
      ];

    await Promise.all(
      fields.map(async ({ field_name, field_schema }) => {
        try {
          await this.client.createPayloadIndex(this.collection, {
            field_name,
            field_schema,
          });
        } catch (error) {
          this.logger.debug({ field_name, error }, 'payload index already exists or failed to create');
        }
      }),
    );
  }

  async upsert(points: QdrantPoint[]): Promise<void> {
    if (points.length === 0) {
      this.logger.warn('attempted to upsert zero qdrant points');
      return;
    }
    await this.ensureCollection();
    await this.client.upsert(this.collection, {
      wait: true,
      points: points.map((point) => ({
        id: point.id,
        vector: point.vector,
        payload: point.payload,
      })),
    });
    this.logger.info({ documentId: points[0]?.payload.document_id, points: points.length }, 'upserted markdown chunks into qdrant');
  }

  async deleteDocument(documentId: string): Promise<void> {
    await this.ensureCollection();
    await this.client.delete(this.collection, {
      wait: true,
      filter: {
        must: [
          {
            key: 'document_id',
            match: {
              value: documentId,
            },
          },
        ],
      },
    });
    this.logger.info({ documentId }, 'deleted markdown chunks from qdrant');
  }
}
