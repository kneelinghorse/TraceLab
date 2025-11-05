import * as amqp from 'amqplib';
import type { ChannelModel, Channel, ConsumeMessage } from 'amqplib';

import type { AppConfig } from '../config.js';
import type { Logger } from '../logger.js';
import type { IngestionTask } from '../types.js';
import type { QueueClient, QueueConsumer, QueueMessage } from './index.js';

export const createRabbitMqQueue = async (
  config: AppConfig,
  logger: Logger,
): Promise<QueueClient<IngestionTask>> => {
  if (!config.rabbitmqUrl) {
    throw new Error('RABBITMQ_URL is required when QUEUE_DRIVER=rabbitmq');
  }

  const connection: ChannelModel = await amqp.connect(config.rabbitmqUrl);
  const channel: Channel = await connection.createChannel();
  await channel.assertQueue(config.rabbitmqQueue, {
    durable: true,
  });

  const publish = async (payload: IngestionTask): Promise<void> => {
    channel.sendToQueue(
      config.rabbitmqQueue,
      Buffer.from(JSON.stringify(payload)),
      { persistent: true },
    );
    logger.debug({ eventId: payload.eventId, action: payload.action }, 'enqueued markdown ingestion task (rabbitmq)');
  };

  const consume = async (consumer: QueueConsumer<IngestionTask>): Promise<void> => {
    await channel.prefetch(config.concurrency);
    await channel.consume(
      config.rabbitmqQueue,
      async (message: ConsumeMessage | null) => {
        if (!message) {
          return;
        }
        let payload: IngestionTask;
        try {
          payload = JSON.parse(message.content.toString()) as IngestionTask;
        } catch (error) {
          logger.error({ error }, 'failed to parse queue message');
          channel.nack(message, false, false);
          return;
        }

        const queueMessage: QueueMessage<IngestionTask> = {
          payload,
          ack: async () => {
            channel.ack(message);
          },
          nack: async (requeue = true) => {
            channel.nack(message, false, requeue);
          },
        };

        try {
          await consumer(queueMessage);
        } catch (error) {
          logger.error({ error }, 'consumer threw error, nacking message');
          await queueMessage.nack();
        }
      },
      { noAck: false },
    );
  };

  const close = async (): Promise<void> => {
    await channel.close();
    await connection.close();
  };

  return {
    publish,
    consume,
    close,
  };
};
