# Document Processing Pipeline

TraceLab's ingestion flow converts an uploaded asset into searchable chunks in five deterministic stages. The pipeline is synchronous today so the `POST /api/v1/documents/{id}/process` endpoint does all the work and returns a structured progress object. Every stage records audit events inside `document_processing_statuses` so the UI and Mission Protocol automations can replay the timeline.

## Stage Breakdown

| Stage        | What happens                                                                 | Status events                                    |
|--------------|------------------------------------------------------------------------------|--------------------------------------------------|
| `extracted`  | Format validation + parsing via `DocumentParser`                             | `in_progress`, `succeeded` (length metadata)     |
| `redacted`   | Optional Presidio pass. When disabled we consciously emit a `skipped` status | `in_progress`, `succeeded`/`skipped`             |
| `chunked`    | `ChunkingService` splits and persists `DocumentChunk` rows                   | `in_progress`, `succeeded`                       |
| `persisted`  | Chunk linkages + DB writes                                                   | `succeeded` (count + avg tokens)                 |
| `embedded`   | Embeddings + Qdrant upsert (new in B7.6)                                     | `in_progress`, `succeeded`/`skipped`/`failed`    |

Successful runs now return:

```json
{
  "status": "completed",
  "stages": {
    "embedded": {
      "status": "success",
      "chunks_embedded": 42,
      "duration_seconds": 1.37,
      "collection": "research_chunks"
    }
  },
  "metrics": {
    "embedding_duration_seconds": 1.37
  }
}
```

`chunks_embedded` and `duration_seconds` satisfy the R7.1 deliverable that the endpoint itself proves embeddings really happened.

## Embedding + Qdrant specifics

R7.1 proved the previous 404s were caused by mixing an API key with an `http://` URL. The fixes implemented here hard stop on that configuration (`QdrantService.__init__` raises with a doc link) and always call `ensure_collection()` before the first `upsert_chunks`. Highlights:

- `EmbeddingService.generate_embeddings_batch()` already implements exponential backoff for OpenAI rate limits. The ingestion service simply reuses it and surfaces any fatal error as a failed stage.
- Embedded payloads include `chunk_id`, `project_id`, `document_id`, `chunk_index`, optional `source_type`, and the float vector. Each chunk stores `embedding_id = str(chunk.id)` for downstream joins.
- The service caches the outcome of `ensure_collection(write_optimized=False)` so only the first document per worker triggers the expensive check.
- When either OpenAI or Qdrant configuration is missing we emit a `skipped` audit entry with a human-readable reason (`Embedding disabled in test environment`, `OPENAI_API_KEY not configured`, etc.).
- Qdrant errors never corrupt the document record: the stage is marked failed, the document stays `embedded=False`, `validation_status` flips to `flagged`, and the exception message is surfaced via the API.

## Required configuration

| Variable                  | Notes                                                                                 |
|---------------------------|---------------------------------------------------------------------------------------|
| `OPENAI_API_KEY`          | Required outside of the test environment. Embedding auto-configuration is disabled when unset. |
| `QDRANT_URL`              | Must be `https://…` whenever `QDRANT_API_KEY` is set (guarded at runtime).            |
| `QDRANT_API_KEY`          | Omit for local `http://localhost:6333` sessions. Match the cloud key in production.  |
| `QDRANT_COLLECTION_NAME`  | Defaults to `research_chunks`; admin endpoints (`/api/v1/admin/init-qdrant`) keep it in sync. |

For provisioning, follow `docs/qdrant-railway-setup.md` (Cloud first, Docker/Railway remain supported for dev). The R7.1 research report (`cmos/missions/research/R7.1_Qdrant-Setup-Investigation.mdR7.1_Qdrant-Setup-Investigation.md`) documents the full root-cause analysis and should accompany any future config edits.

## Validation workflow

1. **Ensure Qdrant readiness**
   - `curl -X POST /api/v1/admin/init-qdrant` (optionally `{"write_optimized": true}` during backfills)
   - `curl /api/v1/admin/health` to verify payload indexes and collection size
2. **Run embedding coverage tests**
   - `pytest tests/test_document_embedding_integration.py`
   - `pytest tests/test_admin_endpoints.py` (guards init/health contracts)
3. **Smoke a document locally**
   - Upload via `/api/v1/documents/upload`
   - `POST /api/v1/documents/{id}/process` and confirm `stages.embedded.status == "success"`
   - Hit the search endpoint or `RetrievalService` to confirm vectors round-trip
4. **Parity + documentation**
   - `python cmos/scripts/validate_parity.py --check`
   - Update telemetry (`telemetry/events/testing-summary.json`) with the pytest output

## Troubleshooting tips

- **`"Api key is used with unsecure connection"`**: the guard in `QdrantService` will now raise before any Qdrant calls. Fix the URL/API key per the table above.
- **Collection missing (404) even after init**: run `POST /api/v1/admin/init-qdrant` again and review the FastAPI logs; the ingestion service also prints a stack trace when `ensure_collection()` fails.
- **Embedding stage stuck on `skipped`**: check the Process response for `reason`. Common causes are `ENVIRONMENT=test` (intended for CI) or a missing `OPENAI_API_KEY`.
- **Partial failures**: Inspect `document_processing_statuses` for the `embedded` entries. The pipeline now records `in_progress`, `failed`, and error context before the outer exception handler promotes the document to `flagged`.

See `docs/implementation_guide.md` for the broader deployment playbook and `cmos/docs/AI-coding-assistant-workflows.md` for Mission Protocol expectations around telemetry and closure.
