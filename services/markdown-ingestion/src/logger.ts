import pino from 'pino';

import { AppConfig } from './config.js';

export type Logger = pino.Logger;

export const createLogger = (config: AppConfig): Logger => {
  return pino({
    level: config.logLevel,
    name: 'markdown-ingestion',
    transport:
      config.environment === 'development'
        ? {
            target: 'pino-pretty',
            options: {
              colorize: true,
              translateTime: true,
            },
          }
        : undefined,
  });
};
