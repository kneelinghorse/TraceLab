-- Performance indexes for high-traffic queries (B8.2 Database Query Optimization)
-- Use CONCURRENTLY in production when applying outside Alembic migrations.

-- Documents
CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents (project_id);

-- Document chunks and embeddings
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_id ON document_chunks (embedding_id);

-- Insights
CREATE INDEX IF NOT EXISTS idx_insights_project_id ON insights (project_id);

-- Insight sources (optimize chunk-to-insight joins)
CREATE INDEX IF NOT EXISTS idx_insight_sources_chunk_id ON insight_sources (chunk_id);

-- Missions
CREATE INDEX IF NOT EXISTS idx_missions_project_status ON missions (project_id, status);
