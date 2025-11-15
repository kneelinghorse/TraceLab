# Hybrid Search Backend

Hybrid search pairs semantic retrieval from Qdrant with PostgreSQL full-text search so result sets balance conceptual similarity with exact keyword coverage. The backend now exposes this capability through the Mission Protocol “Hybrid Search Backend” deliverables.

## Data Model & Migration

- `alembic/versions/006_add_fulltext_search.py` adds a generated `content_tsv` column to `document_chunks` plus a GIN index. PostgreSQL keeps the column current by recomputing `to_tsvector('english', coalesce(content, ''))` whenever chunk content changes.
- The SQLAlchemy `DocumentChunk` model mirrors this column so downstream tooling can reason about it (e.g., schema inspection, migrations).

## Service Architecture

`app/services/hybrid_search.py` coordinates all retrieval modes:

1. **Semantic mode** delegates directly to the existing `RetrievalService`/Qdrant path. Documents return with similarity scores and embeddings for downstream compression.
2. **Keyword mode** runs a PostgreSQL full-text query using `websearch_to_tsquery`. Results are scored with `ts_rank_cd` and normalized into `[0, 1]`.
3. **Hybrid mode** runs both retrieval strategies (each pulling `top_k * multiplier` items, multiplier defaults to `2`). Scores are min-max normalized independently, then combined with configurable weights:

```
combined_score = (semantic_norm * semantic_weight) + (keyword_norm * keyword_weight)
```

Entries present in one modality retain their normalized score, with `search_mode` metadata indicating whether semantic, keyword, or hybrid contributions drove the final rank. The merged list is sorted by `combined_score` before truncating to `top_k`.

## Configuration

`app/core/config.py` exposes environment overrides:

- `HYBRID_SEARCH_SEMANTIC_WEIGHT` (default `0.7`)
- `HYBRID_SEARCH_KEYWORD_WEIGHT` (default `0.3`)
- `HYBRID_SEARCH_KEYWORD_LANGUAGE` (default `"english"`)
- `HYBRID_SEARCH_RESULT_MULTIPLIER` (default `2`, controls the oversampling factor for semantic + keyword pools)

Weights are normalized internally, so any positive ratio works.

## API & Schema Changes

- `RagQuery` now accepts `search_mode`, a literal with values `semantic`, `keyword`, or `hybrid`.
- `/api/v1/search` forwards `search_mode` to `RagService`. Responses (`RagResponse`) echo the resolved mode for observability.
- Cache keys include `search_mode`, so semantic and hybrid answers do not collide.

Clients simply append `"search_mode": "hybrid"` (or `"keyword"`) to existing payloads to activate new behavior.

## Testing & Benchmarks

- `tests/test_hybrid_search.py` covers normalization, weighting, and error handling.
- `tests/test_rag_service.py` gained coverage ensuring `search_mode` propagates through the full RAG stack and API.
- Run `pytest tests/test_hybrid_search.py tests/test_rag_service.py` before promoting changes.
- Performance telemetry is captured in `cmos/telemetry/events/sprint-09-hybrid-search.jsonl`. Each entry logs query type, timing, and delta vs. semantic-only runs so we can confirm the `<200ms` latency budget and ≥15% precision lift.

## Operational Notes

- PostgreSQL full-text indexes must be deployed via `alembic upgrade head` before enabling keyword/hybrid modes on production.
- The hybrid search service only opens a database session when keyword querying is required; semantic mode incurs no extra DB overhead.
- `search_mode` is persisted inside cached RAG responses, so existing caches remain valid and easy to invalidate by mode.
