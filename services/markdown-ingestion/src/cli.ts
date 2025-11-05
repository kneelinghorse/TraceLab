#!/usr/bin/env node
import { Command } from 'commander';

import { loadConfig } from './config.js';
import { createLogger } from './logger.js';
import { createQueueClient } from './queue/index.js';
import { WatcherService } from './watchers/watcher.js';
import { startWorker } from './workers/worker.js';
import { runBackfill } from './backfill.js';
import { Telemetry } from './telemetry/telemetry.js';

const program = new Command();

program
  .name('ingest')
  .description('TraceLab Markdown ingestion pipeline CLI')
  .option('-c, --config <path>', 'Optional configuration file (env file)');

program
  .command('watch')
  .description('Start chokidar watcher and enqueue Markdown ingestion tasks')
  .action(async () => {
    const config = loadConfig();
    const logger = createLogger(config);
    const telemetry = new Telemetry(config);
    await telemetry.start();
    const queue = await createQueueClient(config, logger);
    const watcher = new WatcherService(config, queue, logger);

    const shutdown = async () => {
      logger.info('shutting down markdown watcher');
      await watcher.stop();
      await queue.close();
      await telemetry.shutdown();
      process.exit(0);
    };

    process.on('SIGINT', () => void shutdown());
    process.on('SIGTERM', () => void shutdown());

    await watcher.start();
    logger.info('markdown watcher running');

    await new Promise(() => {
      /* keep process running */
    });
  });

program
  .command('worker')
  .description('Run ingestion worker that consumes queue tasks')
  .action(async () => {
    await startWorker();
  });

program
  .command('backfill')
  .description('Enqueue backfill tasks for existing Markdown corpus')
  .action(async () => {
    await runBackfill();
  });

program.parseAsync(process.argv).catch((error) => {
  console.error('ingestion command failed', error);
  process.exit(1);
});
