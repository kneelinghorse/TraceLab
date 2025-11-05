# Markdown Ingestion Pipeline

This package provides the chokidar → queue → unified/remark pipeline required by mission B2.3a.  It watches Markdown research directories, transforms files into Qdrant-ready payloads, and exposes CLI commands for local development or deployment automation.

## Features

- **File watcher** using `chokidar` with debounced events and ignore patterns.
- **Queue abstraction** with an in-memory implementation for local use and RabbitMQ support for durable backends.
- **Markdown parser + chunker** leveraging `remark-parse`, `remark-frontmatter`, and heading-aware chunk segmentation.
- **Embedding + Qdrant integration** that generates OpenAI embeddings, derives stable chunk IDs, and upserts payloads aligned with the R2.2 schema.
- **Backfill utility** to enqueue historical Markdown documents.
- **Telemetry hooks** via OpenTelemetry counters/histograms plus structured logging through `pino`.

## Directory structure

```
src/
├── backfill.ts                # CLI entry for corpus backfill
├── cli.ts                     # Commander-based CLI
├── config.ts                  # Environment + zod validation
├── logger.ts                  # Shared pino logger
├── markdown/                  # Parser + chunker utilities
├── queue/                     # Queue abstractions (memory + RabbitMQ)
├── services/                  # Embedding, Qdrant, metrics, ingestion orchestrator
├── telemetry/                 # OpenTelemetry facade
├── watchers/                  # chokidar watcher service
└── workers/                   # Queue consumer bootstrap
```

## Configuration

All configuration is env-driven. Defaults target local development with the research corpus in `cmos/missions/research`.

| Variable | Description | Default |
| --- | --- | --- |
| `INGESTION_WATCH_PATHS` | Comma-separated directories to watch | `cmos/missions/research`
| `INGESTION_IGNORE_PATTERNS` | Comma-separated globs to skip | `**/.git/**,**/node_modules/**,**/.DS_Store`
| `INGESTION_DEBOUNCE_MS` | Debounce window for watcher events | `750`
| `INGESTION_QUEUE_DRIVER` | `memory` or `rabbitmq` | `memory`
| `RABBITMQ_URL` | Broker connection string (rabbitmq mode) | _required for rabbitmq_
| `RABBITMQ_QUEUE` | Queue name | `markdown_ingestion`
| `MARKDOWN_PROJECT_ID` | Default project UUID payload | _(optional)_
| `MARKDOWN_DOC_TYPE` | Default `doc_type` metadata | `research_markdown`
| `OPENAI_API_KEY` | Token for embeddings | _required_
| `OPENAI_EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small`
| `OPENAI_EMBED_BATCH_SIZE` | Batch size per embedding request | `16`
| `OPENAI_EMBEDDING_DIMENSION` | Vector dimension | `1536`
| `QDRANT_URL` | Qdrant base URL | `http://localhost:6333`
| `QDRANT_API_KEY` | API key for Qdrant | _(optional)_
| `QDRANT_COLLECTION` | Collection name | `research_markdown_chunks`
| `MARKDOWN_CHUNK_MAX_TOKENS` | Max characters per chunk | `900`
| `MARKDOWN_CHUNK_MIN_TOKENS` | Minimum characters per chunk | `120`
| `MARKDOWN_CHUNK_OVERLAP` | Character overlap when splitting | `150`
| `INGESTION_CONCURRENCY` | Queue consumer concurrency (RabbitMQ prefetch) | `4`
| `INGESTION_MAX_CONCURRENT_EMBEDDINGS` | Parallel embedding requests | `4`
| `MARKDOWN_DOCUMENT_NAMESPACE` | UUID namespace used for deterministic IDs | `a4a7698d-9094-47ea-9725-1852d4b0df76`
| `INGESTION_LOG_LEVEL` | pino log level | `info`
| `INGESTION_TELEMETRY_ENABLED` | `true/false` flag to surface OTEL diagnostics | `false`

## CLI commands

All commands run via `npm run` or directly with `tsx`:

```bash
npm install
npm run build        # optional: compile to dist
npm run start:worker # start ingestion worker
npm run start:watcher# start chokidar watcher
npm run backfill     # enqueue historical markdown corpus
```

Alternatively, `npx tsx src/cli.ts <command>` works without scripts.

### Watcher

```
npm run start:watcher
```

- Monitors configured directories.
- Emits debounced `upsert` tasks on add/change and `delete` tasks on unlink.
- Works with the in-memory queue by default. Combine with the worker process for end-to-end ingestion.

### Worker

```
npm run start:worker
```

- Consumes queue tasks, parses Markdown via unified/remark, chunks content, generates embeddings via OpenAI, and upserts payloads to Qdrant.
- Retries are delegated to the queue backend (RabbitMQ). The in-memory queue requeues on failure.

### Backfill

```
npm run backfill
```

- Recursively scans watch paths for `.md`/`.markdown` files and enqueues `upsert` tasks.
- Useful for initial corpus population before enabling the watcher.

## Telemetry

Counters/histograms are created through the OpenTelemetry API. To export data, register an SDK (e.g. `@opentelemetry/sdk-node`) in the hosting process and set the standard OTEL environment variables. Without an SDK the instrumentation remains a no-op while retaining compatibility.

## Development notes

- The project targets Node.js 18+ with native ESM modules.
- TypeScript build outputs to `dist/` (`npm run build`). Runtime commands rely on `tsx` for convenience.
- The chunker preserves heading hierarchy and ensures deterministic chunk hashes. Adjust thresholds in `config.ts` to tune chunk sizes.
- RabbitMQ support is optional. In-memory mode is sufficient for local experimentation and CI pipelines.
