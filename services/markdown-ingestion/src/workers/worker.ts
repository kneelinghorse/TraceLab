import { loadConfig } from '../config.js';
import { createLogger } from '../logger.js';
import { createQueueClient } from '../queue/index.js';
import { Telemetry } from '../telemetry/telemetry.js';
import { EmbeddingService } from '../services/embedding-service.js';
import { QdrantIngestionClient } from '../services/qdrant-service.js';
import { IngestionMetrics } from '../services/metrics.js';
import { MarkdownIngestionService } from '../services/markdown-ingestion-service.js';

export const startWorker = async (): Promise<void> => {
  const config = loadConfig();
  const logger = createLogger(config);
  const telemetry = new Telemetry(config);
  await telemetry.start();

  const queue = await createQueueClient(config, logger);
  const embeddings = new EmbeddingService(config, logger);
  const qdrant = new QdrantIngestionClient(config, logger);
  const metrics = new IngestionMetrics(telemetry);
  const ingestion = new MarkdownIngestionService(config, logger, embeddings, qdrant, metrics);

  logger.info('markdown ingestion worker starting');

  const shutdown = async () => {
    logger.info('shutting down markdown ingestion worker');
    await queue.close();
    await telemetry.shutdown();
  };

  process.on('SIGINT', () => {
    shutdown()
      .then(() => process.exit(0))
      .catch((error) => {
        logger.error({ error }, 'failed to shutdown gracefully');
        process.exit(1);
      });
  });

  process.on('SIGTERM', () => {
    shutdown()
      .then(() => process.exit(0))
      .catch((error) => {
        logger.error({ error }, 'failed to shutdown gracefully');
        process.exit(1);
      });
  });

  await queue.consume(async (message) => {
    try {
      await ingestion.handle(message.payload);
      await message.ack();
    } catch (error) {
      logger.error({ error, task: message.payload }, 'ingestion task failed');
      await message.nack();
    }
  });
};
