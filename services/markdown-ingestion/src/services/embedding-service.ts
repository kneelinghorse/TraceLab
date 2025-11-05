import OpenAI from 'openai';
import PQueue from 'p-queue';

import type { AppConfig } from '../config.js';
import type { Logger } from '../logger.js';

export class EmbeddingService {
  private readonly client: OpenAI;
  private readonly batchSize: number;
  private readonly queue: PQueue;

  constructor(config: AppConfig, private readonly logger: Logger) {
    if (!config.openaiApiKey) {
      throw new Error('OPENAI_API_KEY is required for Markdown ingestion');
    }
    this.client = new OpenAI({
      apiKey: config.openaiApiKey,
    });
    this.batchSize = config.openaiBatchSize;
    this.queue = new PQueue({ concurrency: config.maxConcurrentEmbeddings });
  }

  async embedTexts(texts: string[], model: string): Promise<number[][]> {
    const results: number[][] = [];
    const batches: string[][] = [];
    for (let i = 0; i < texts.length; i += this.batchSize) {
      batches.push(texts.slice(i, i + this.batchSize));
    }

    await Promise.all(
      batches.map((batch, batchIndex) =>
        this.queue.add(async () => {
          this.logger.debug({ batchIndex, size: batch.length }, 'requesting embeddings');
          const response = await this.client.embeddings.create({
            model,
            input: batch,
          });
          response.data.forEach((item, innerIndex) => {
            results[batchIndex * this.batchSize + innerIndex] = item.embedding as number[];
          });
        }),
      ),
    );

    return results;
  }
}
