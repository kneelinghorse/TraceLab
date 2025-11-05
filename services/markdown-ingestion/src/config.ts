import { config as loadEnv } from 'dotenv';
import { z } from 'zod';

loadEnv();

const commaSeparated = (value: string | undefined, fallback: string[]): string[] => {
  if (!value || !value.trim()) {
    return fallback;
  }
  return value
    .split(',')
    .map((segment) => segment.trim())
    .filter((segment) => segment.length > 0);
};

const ConfigSchema = z.object({
  environment: z.string().default(process.env.NODE_ENV ?? 'development'),
  watchPaths: z
    .string()
    .optional()
    .transform((value) => commaSeparated(value, ['cmos/missions/research'])),
  ignorePatterns: z
    .string()
    .optional()
    .transform((value) => commaSeparated(value, ['**/.git/**', '**/node_modules/**', '**/.DS_Store'])),
  debounceMs: z
    .string()
    .transform((value) => Number.parseInt(value, 10))
    .catch(750),
  queueDriver: z
    .enum(['memory', 'rabbitmq'])
    .catch((process.env.INGESTION_QUEUE_DRIVER as 'memory' | 'rabbitmq' | undefined) ?? 'memory'),
  rabbitmqUrl: z.string().optional().catch(process.env.RABBITMQ_URL),
  rabbitmqQueue: z.string().default(process.env.RABBITMQ_QUEUE ?? 'markdown_ingestion'),
  projectId: z.string().uuid().optional().catch(process.env.MARKDOWN_PROJECT_ID),
  defaultDocType: z.string().default(process.env.MARKDOWN_DOC_TYPE ?? 'research_markdown'),
  openaiApiKey: z.string().optional().catch(process.env.OPENAI_API_KEY),
  openaiEmbeddingModel: z.string().default(process.env.OPENAI_EMBEDDING_MODEL ?? 'text-embedding-3-small'),
  openaiBatchSize: z
    .string()
    .transform((value) => Number.parseInt(value, 10))
    .catch(16),
  openaiEmbeddingDimension: z
    .string()
    .transform((value) => Number.parseInt(value, 10))
    .catch(1536),
  qdrantUrl: z.string().default(process.env.QDRANT_URL ?? 'http://localhost:6333'),
  qdrantApiKey: z.string().optional().catch(process.env.QDRANT_API_KEY),
  qdrantCollection: z.string().default(process.env.QDRANT_COLLECTION ?? 'research_markdown_chunks'),
  chunkMaxTokens: z
    .string()
    .transform((value) => Number.parseInt(value, 10))
    .catch(900),
  chunkMinTokens: z
    .string()
    .transform((value) => Number.parseInt(value, 10))
    .catch(120),
  chunkOverlap: z
    .string()
    .transform((value) => Number.parseInt(value, 10))
    .catch(150),
  concurrency: z
    .string()
    .transform((value) => Number.parseInt(value, 10))
    .catch(4),
  maxConcurrentEmbeddings: z
    .string()
    .transform((value) => Number.parseInt(value, 10))
    .catch(4),
  telemetryEnabled: z
    .string()
    .optional()
    .transform((value) => value === '1' || value?.toLowerCase() === 'true')
    .catch(process.env.INGESTION_TELEMETRY_ENABLED === '1'),
  otlpEndpoint: z.string().optional().catch(process.env.OTEL_EXPORTER_OTLP_ENDPOINT),
  otlpHeaders: z.string().optional().catch(process.env.OTEL_EXPORTER_OTLP_HEADERS),
  logLevel: z.string().default(process.env.INGESTION_LOG_LEVEL ?? process.env.LOG_LEVEL ?? 'info'),
  documentNamespace: z
    .string()
    .uuid()
    .catch(process.env.MARKDOWN_DOCUMENT_NAMESPACE ?? 'a4a7698d-9094-47ea-9725-1852d4b0df76'),
});

export type AppConfig = z.infer<typeof ConfigSchema> & {
  watchPaths: string[];
  ignorePatterns: string[];
};

export const loadConfig = (): AppConfig => {
  const parsed = ConfigSchema.parse({
    watchPaths: process.env.INGESTION_WATCH_PATHS,
    ignorePatterns: process.env.INGESTION_IGNORE_PATTERNS,
    debounceMs: process.env.INGESTION_DEBOUNCE_MS,
    queueDriver: process.env.INGESTION_QUEUE_DRIVER,
    rabbitmqUrl: process.env.RABBITMQ_URL,
    rabbitmqQueue: process.env.RABBITMQ_QUEUE,
    projectId: process.env.MARKDOWN_PROJECT_ID,
    defaultDocType: process.env.MARKDOWN_DOC_TYPE,
    openaiApiKey: process.env.OPENAI_API_KEY,
    openaiEmbeddingModel: process.env.OPENAI_EMBEDDING_MODEL,
    openaiBatchSize: process.env.OPENAI_EMBED_BATCH_SIZE,
    openaiEmbeddingDimension: process.env.OPENAI_EMBEDDING_DIMENSION,
    qdrantUrl: process.env.QDRANT_URL,
    qdrantApiKey: process.env.QDRANT_API_KEY,
    qdrantCollection: process.env.QDRANT_COLLECTION,
    chunkMaxTokens: process.env.MARKDOWN_CHUNK_MAX_TOKENS,
    chunkMinTokens: process.env.MARKDOWN_CHUNK_MIN_TOKENS,
    chunkOverlap: process.env.MARKDOWN_CHUNK_OVERLAP,
    concurrency: process.env.INGESTION_CONCURRENCY,
    maxConcurrentEmbeddings: process.env.INGESTION_MAX_CONCURRENT_EMBEDDINGS,
    telemetryEnabled: process.env.INGESTION_TELEMETRY_ENABLED,
    otlpEndpoint: process.env.OTEL_EXPORTER_OTLP_ENDPOINT,
    otlpHeaders: process.env.OTEL_EXPORTER_OTLP_HEADERS,
    logLevel: process.env.INGESTION_LOG_LEVEL ?? process.env.LOG_LEVEL,
    documentNamespace: process.env.MARKDOWN_DOCUMENT_NAMESPACE,
  });

  return {
    ...parsed,
    watchPaths: parsed.watchPaths,
    ignorePatterns: parsed.ignorePatterns,
  };
};
