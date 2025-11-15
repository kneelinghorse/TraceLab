# Database Optimization Notes (Mission B8.2)

## What changed
- Added performance indexes for hot paths: documents (project_id), document_chunks (document_id, embedding_id), insights (project_id), insight_sources (chunk_id), missions (project_id, status). See `alembic/versions/005_performance_indexes.py` and `app/db/indexes.sql`.
- Hardened ORM mapping so the same indexes exist when running `Base.metadata.create_all` (test SQLite parity).
- Document listing now uses `load_only` to avoid hydrating large `content`/`raw_content` fields and to reduce payload size for paginated APIs.
- Document detail retrieval preloads related chunks, tags, and processing events with `selectinload` to cut down on follow-up queries.

## How to apply
1. Run `alembic upgrade head` (or `alembic upgrade 005_performance_indexes` if pinning).
2. For production Postgres, prefer `CREATE INDEX CONCURRENTLY` when applying `app/db/indexes.sql` outside Alembic.

## Quick validation
- Check indexes: `psql -c "\\di + idx_*"` or `python - <<'PY'\nfrom sqlalchemy import create_engine, inspect\nengine = create_engine('postgresql://...')\nprint({i['name']: i['column_names'] for i in inspect(engine).get_indexes('documents')})\nPY`
- Run automated checks: `pytest tests/performance/test_db_query_optimizations.py`.
- Optional profiling: enable `pg_stat_statements` and inspect top calls via `SELECT query, total_exec_time, calls FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 10;`.

## Notes and next steps
- Baseline/after metrics were not captured in this workspace; collect them after deploying to Postgres with representative data.
- If document list filters on `processed` become hot, consider a composite index `(project_id, processed, uploaded_at desc)` once real query plans confirm the need.
- Keep an eye on chunk joins that use `chunk_id` first; the new `idx_insight_sources_chunk_id` covers that path. Use `EXPLAIN (ANALYZE, BUFFERS)` to verify planner choices.
