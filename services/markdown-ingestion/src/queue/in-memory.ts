import { EventEmitter } from 'events';

import type { Logger } from '../logger.js';
import type { IngestionTask } from '../types.js';
import type { QueueClient, QueueConsumer, QueueMessage } from './index.js';

const CHANNEL_EVENT = 'message';

export const createInMemoryQueue = (logger: Logger): QueueClient<IngestionTask> => {
  const emitter = new EventEmitter();
  const buffer: IngestionTask[] = [];
  let consuming = false;

  const publish = async (payload: IngestionTask): Promise<void> => {
    buffer.push(payload);
    logger.debug({ eventId: payload.eventId, action: payload.action }, 'enqueued markdown ingestion task');
    process.nextTick(() => emitter.emit(CHANNEL_EVENT));
  };

  const consume = async (consumer: QueueConsumer<IngestionTask>): Promise<void> => {
    if (consuming) {
      throw new Error('In-memory queue already has an active consumer');
    }
    consuming = true;

    const handleNext = async () => {
      const nextItem = buffer.shift();
      if (!nextItem) {
        return;
      }
      const message: QueueMessage<IngestionTask> = {
        payload: nextItem,
        ack: async () => {
          /* no-op */
        },
        nack: async (requeue = true) => {
          if (requeue) {
            buffer.push(nextItem);
            process.nextTick(() => emitter.emit(CHANNEL_EVENT));
          }
        },
      };

      try {
        await consumer(message);
      } catch (error) {
        logger.error({ error }, 'consumer threw error, requeueing message');
        await message.nack();
      }
    };

    const listener = async () => {
      await handleNext();
    };

    emitter.on(CHANNEL_EVENT, listener);

    while (consuming) {
      if (buffer.length === 0) {
        await new Promise((resolve) => setTimeout(resolve, 50));
        continue;
      }
      await handleNext();
    }
  };

  const close = async (): Promise<void> => {
    consuming = false;
    emitter.removeAllListeners(CHANNEL_EVENT);
  };

  return {
    publish,
    consume,
    close,
  };
};
