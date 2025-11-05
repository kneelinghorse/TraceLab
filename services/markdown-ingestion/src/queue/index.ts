import { AppConfig } from '../config.js';
import type { Logger } from '../logger.js';
import type { IngestionTask } from '../types.js';
import { createRabbitMqQueue } from './rabbitmq.js';
import { createInMemoryQueue } from './in-memory.js';

export interface QueueMessage<T> {
  ack: () => Promise<void>;
  nack: (requeue?: boolean) => Promise<void>;
  payload: T;
}

export type QueueConsumer<T> = (message: QueueMessage<T>) => Promise<void>;

export interface QueueClient<T> {
  publish(payload: T): Promise<void>;
  consume(consumer: QueueConsumer<T>): Promise<void>;
  close(): Promise<void>;
}

export const createQueueClient = async (
  config: AppConfig,
  logger: Logger,
): Promise<QueueClient<IngestionTask>> => {
  if (config.queueDriver === 'rabbitmq') {
    return createRabbitMqQueue(config, logger);
  }
  return createInMemoryQueue(logger);
};
