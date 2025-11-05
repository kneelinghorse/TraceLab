import { globby } from 'globby';
import path from 'path';
import { randomUUID } from 'crypto';
import { v5 as uuidv5 } from 'uuid';

import { loadConfig } from './config.js';
import { createLogger } from './logger.js';
import { createQueueClient } from './queue/index.js';
import { Telemetry } from './telemetry/telemetry.js';
import type { IngestionTask } from './types.js';

export const runBackfill = async (): Promise<void> => {
  const config = loadConfig();
  const logger = createLogger(config);
  const telemetry = new Telemetry(config);
  await telemetry.start();

  const queue = await createQueueClient(config, logger);

  try {
    const patterns = config.watchPaths.flatMap((watchPath) => [
      path.join(watchPath, '**/*.md'),
      path.join(watchPath, '**/*.markdown'),
    ]);
    const files = await globby(patterns, {
      ignore: config.ignorePatterns,
      onlyFiles: true,
      absolute: true,
    });

    logger.info({ count: files.length }, 'backfill: discovered markdown files');

    const now = new Date().toISOString();

    for (const absolutePath of files) {
      const relativePath = path.relative(process.cwd(), absolutePath).split(path.sep).join('/');
      const documentId = uuidv5(relativePath, config.documentNamespace);
      const task: IngestionTask = {
        eventId: randomUUID(),
        action: 'upsert',
        absolutePath,
        sourceUri: relativePath,
        documentId,
        projectId: config.projectId,
        docType: config.defaultDocType,
        updatedAt: now,
      };
      await queue.publish(task);
    }

    logger.info({ count: files.length }, 'backfill: enqueued markdown ingestion tasks');
  } finally {
    await queue.close();
    await telemetry.shutdown();
  }
};
