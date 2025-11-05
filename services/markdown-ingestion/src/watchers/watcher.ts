import chokidar, { FSWatcher } from 'chokidar';
import { randomUUID } from 'crypto';
import path from 'path';

import type { AppConfig } from '../config.js';
import type { Logger } from '../logger.js';
import type { IngestionTask } from '../types.js';
import type { QueueClient } from '../queue/index.js';
import { v5 as uuidv5 } from 'uuid';

export class WatcherService {
  private watcher?: FSWatcher;
  private readonly debounceTimers = new Map<string, NodeJS.Timeout>();

  constructor(
    private readonly config: AppConfig,
    private readonly queue: QueueClient<IngestionTask>,
    private readonly logger: Logger,
  ) {}

  async start(): Promise<void> {
    if (this.watcher) {
      throw new Error('watcher already started');
    }

    this.logger.info({ watchPaths: this.config.watchPaths }, 'starting markdown watcher');

    this.watcher = chokidar.watch(this.config.watchPaths, {
      ignored: this.config.ignorePatterns,
      ignoreInitial: false,
      persistent: true,
      awaitWriteFinish: {
        stabilityThreshold: this.config.debounceMs,
        pollInterval: Math.max(100, Math.round(this.config.debounceMs / 2)),
      },
    });

    this.watcher.on('add', (filePath) => this.scheduleUpsert('add', filePath));
    this.watcher.on('change', (filePath) => this.scheduleUpsert('change', filePath));
    this.watcher.on('unlink', (filePath) => this.handleDelete(filePath));

    await new Promise<void>((resolve, reject) => {
      if (!this.watcher) {
        reject(new Error('watcher not created'));
        return;
      }
      this.watcher
        .on('ready', () => {
          this.logger.info('markdown watcher ready');
          resolve();
        })
        .on('error', (error) => {
          this.logger.error({ error }, 'markdown watcher error');
          reject(error);
        });
    });
  }

  async stop(): Promise<void> {
    if (!this.watcher) {
      return;
    }
    this.debounceTimers.forEach((timer) => clearTimeout(timer));
    this.debounceTimers.clear();
    await this.watcher.close();
    this.watcher = undefined;
    this.logger.info('markdown watcher stopped');
  }

  private async scheduleUpsert(eventType: 'add' | 'change', filePath: string): Promise<void> {
    if (!this.isMarkdownFile(filePath)) {
      return;
    }
    const absolutePath = path.resolve(filePath);
    const pendingTimer = this.debounceTimers.get(absolutePath);
    if (pendingTimer) {
      clearTimeout(pendingTimer);
    }
    const timer = setTimeout(() => {
      this.enqueueUpsert(eventType, absolutePath).catch((error) => {
        this.logger.error({ error, path: absolutePath }, 'failed to enqueue markdown ingestion task');
      });
    }, this.config.debounceMs);
    this.debounceTimers.set(absolutePath, timer);
  }

  private async enqueueUpsert(eventType: 'add' | 'change', absolutePath: string): Promise<void> {
    this.debounceTimers.delete(absolutePath);
    const sourceUri = this.toSourceUri(absolutePath);
    const documentId = uuidv5(sourceUri, this.config.documentNamespace);
    const task: IngestionTask = {
      eventId: randomUUID(),
      action: 'upsert',
      absolutePath,
      sourceUri,
      documentId,
      docType: undefined,
      projectId: this.config.projectId,
      updatedAt: new Date().toISOString(),
    };
    await this.queue.publish(task);
    this.logger.debug({ eventType, documentId, sourceUri }, 'queued markdown ingestion task');
  }

  private async handleDelete(filePath: string): Promise<void> {
    if (!this.isMarkdownFile(filePath)) {
      return;
    }
    const absolutePath = path.resolve(filePath);
    const pendingTimer = this.debounceTimers.get(absolutePath);
    if (pendingTimer) {
      clearTimeout(pendingTimer);
      this.debounceTimers.delete(absolutePath);
    }
    const sourceUri = this.toSourceUri(absolutePath);
    const documentId = uuidv5(sourceUri, this.config.documentNamespace);
    const task: IngestionTask = {
      eventId: randomUUID(),
      action: 'delete',
      absolutePath,
      sourceUri,
      documentId,
      projectId: this.config.projectId,
      updatedAt: new Date().toISOString(),
    };
    await this.queue.publish(task);
    this.logger.debug({ documentId, sourceUri }, 'queued markdown deletion task');
  }

  private isMarkdownFile(filePath: string): boolean {
    return filePath.endsWith('.md') || filePath.endsWith('.markdown');
  }

  private toSourceUri(absolutePath: string): string {
    const relativePath = path.relative(process.cwd(), absolutePath);
    return relativePath.split(path.sep).join('/');
  }
}
