# Qdrant Resilience & Reprocessing Strategy

## Executive Summary

**Can we fully rebuild Qdrant from PostgreSQL?** ✅ **YES**

PostgreSQL stores all data required to regenerate embeddings and rebuild the Qdrant collection:
- Complete document content (redacted text)
- Chunk boundaries (start_char, end_char, chunk_index)
- Chunk content (the actual text for each chunk)
- Document/project relationships

**Embeddings are NOT stored in PostgreSQL** — only the `embedding_id` reference (which equals the chunk UUID). This is a deliberate design choice: embeddings can always be regenerated from content.

---

## Current Architecture

### Data Flow

```
Document Upload → Parse → Redact → Chunk → Generate Embeddings → Store in Qdrant
                    ↓         ↓        ↓                              ↓
               [content]  [content] [document_chunks]          [Qdrant vectors]
                                     PostgreSQL                   + payloads
```

### What PostgreSQL Stores

| Table | Key Fields | Purpose |
|-------|------------|---------|
| `documents` | `id`, `content`, `project_id`, `embedded` | Full redacted text, processing flags |
| `document_chunks` | `id`, `document_id`, `content`, `chunk_index`, `embedding_id`, `start_char`, `end_char` | Chunk text and boundaries |

### What Qdrant Stores

| Field | Source | Description |
|-------|--------|-------------|
| `id` | `chunk.id` | Point ID = Chunk UUID |
| `vector` | OpenAI API | 1536-dim embedding (text-embedding-3-small) |
| `payload.content` | `chunk.content` | Chunk text (for retrieval display) |
| `payload.document_id` | `chunk.document_id` | Foreign key reference |
| `payload.project_id` | `document.project_id` | For filtering |
| `payload.chunk_index` | `chunk.chunk_index` | Position in document |
| `payload.source_type` | `document.source_type` | Optional metadata |

---

## Reprocessing Capabilities

### Current State: Partial Support

| Capability | Status | Notes |
|------------|--------|-------|
| Re-chunk from content | ✅ Available | `ChunkingService` is deterministic |
| Re-embed chunks | ✅ Available | `EmbeddingService.generate_embeddings_batch()` |
| Upsert to Qdrant | ✅ Available | `QdrantService.upsert_chunks()` |
| Single document reprocess | ⚠️ Manual | Must delete chunks, call `/process` endpoint |
| Bulk reprocess all docs | ❌ No script | **GAP**: Need `scripts/reprocess_embeddings.py` |
| Idempotent reindex | ✅ Safe | Upsert uses chunk UUID as point ID |

### Idempotency Guarantee

The system is idempotent because:
1. Chunk UUIDs are generated at chunk creation time and stored in PostgreSQL
2. `embedding_id` = chunk UUID = Qdrant point ID
3. `QdrantService.upsert_chunks()` uses upsert semantics
4. Re-running the same chunks will overwrite with identical data

---

## Reprocessing Procedure

### Single Document Reprocessing

```bash
# 1. Get the document ID you want to reprocess
DOCUMENT_ID="<uuid>"

# 2. Delete existing chunks (cascade will remove from memory, Qdrant stays stale)
psql -c "DELETE FROM document_chunks WHERE document_id = '$DOCUMENT_ID';"

# 3. Reset processing flags
psql -c "UPDATE documents SET chunked = false, embedded = false WHERE id = '$DOCUMENT_ID';"

# 4. Call process endpoint to rechunk and re-embed
curl -X POST "http://localhost:8000/api/v1/documents/$DOCUMENT_ID/process" \
  -H "Authorization: Bearer $TOKEN"
```

### Full Collection Rebuild (Manual Steps)

Until `scripts/reprocess_embeddings.py` exists, follow this procedure:

```python
# reprocess_all.py (one-time script)
import sys
sys.path.insert(0, '.')

from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.services.embedding_service import get_embedding_service
from app.services.qdrant_service import get_qdrant_service

def reprocess_all_embeddings():
    """Regenerate all embeddings from PostgreSQL chunks."""
    db = next(get_db())
    embedding_service = get_embedding_service()
    qdrant_service = get_qdrant_service()

    # Ensure collection exists
    qdrant_service.ensure_collection(write_optimized=True)

    # Process documents in batches
    documents = db.query(Document).filter(Document.chunked == True).all()

    for doc in documents:
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == doc.id
        ).order_by(DocumentChunk.chunk_index).all()

        if not chunks:
            continue

        # Generate embeddings
        texts = [c.content for c in chunks]
        embeddings = embedding_service.generate_embeddings_batch(texts)

        # Prepare Qdrant payload
        payload = []
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding_id = str(chunk.id)
            payload.append({
                "chunk_id": chunk.id,
                "embedding": embedding,
                "content": chunk.content,
                "document_id": doc.id,
                "project_id": doc.project_id,
                "chunk_index": chunk.chunk_index,
                "source_type": doc.source_type,
            })

        # Upsert to Qdrant
        qdrant_service.upsert_chunks(payload)
        doc.embedded = True
        db.commit()
        print(f"Reprocessed {doc.name}: {len(chunks)} chunks")

    # Enable indexing after bulk import
    qdrant_service.enable_indexing_and_quantization()
    print("Rebuild complete!")

if __name__ == "__main__":
    reprocess_all_embeddings()
```

---

## Time & Cost Estimates

### Current Scale (~100-200 Documents)

| Operation | Estimate | Notes |
|-----------|----------|-------|
| Full rebuild time | **10-30 minutes** | Dominated by OpenAI API calls |
| OpenAI API cost | **$2-5** | ~1M tokens @ $0.02/1K (small model) |
| Qdrant rebuild | **< 1 minute** | Upsert is fast |

### Assumptions
- Average document: 5,000 tokens → ~7 chunks
- 200 documents × 7 chunks = 1,400 chunks
- 1,400 chunks × 750 tokens avg = ~1M tokens
- Embedding throughput: ~100 chunks/second (batched)

### At 10x Scale (~2,000 Documents)

| Operation | Estimate | Notes |
|-----------|----------|-------|
| Full rebuild time | **2-5 hours** | Rate limits may slow further |
| OpenAI API cost | **$20-50** | ~10M tokens |
| Qdrant rebuild | **5-10 minutes** | Still fast |

---

## Gap Analysis

### Missing Capabilities

| Gap | Priority | Recommendation |
|-----|----------|----------------|
| No bulk reprocess script | **HIGH** | Create `scripts/reprocess_embeddings.py` |
| No Qdrant collection export | MEDIUM | Qdrant Cloud doesn't support user backups on free tier |
| No embedding backup in PG | LOW | See cost/benefit analysis below |

### Should We Store Embeddings in PostgreSQL?

**Recommendation: NO** (for now)

| Factor | Analysis |
|--------|----------|
| Storage cost | 1536 floats × 4 bytes × 14K chunks = ~80 MB (manageable) |
| Rebuild speed | Storing embeddings saves OpenAI calls but adds PG complexity |
| Data freshness | Model changes require re-embedding anyway |
| Current risk | Qdrant loss = $5 and 30 min to rebuild |

**Revisit if:**
- Scale exceeds 10K documents
- OpenAI costs become significant
- Rebuild time exceeds acceptable RTO

---

## Qdrant Cloud Limitations

Current tier (free/starter) limitations:
- ❌ No user-initiated backups
- ❌ No snapshot export
- ✅ Automatic provider backups (not user-accessible)
- ✅ Data persisted across restarts

**Mitigation**: PostgreSQL is our source of truth. Qdrant can always be rebuilt.

---

## Recovery Procedures

### Scenario 1: Qdrant Collection Corrupted/Lost

1. Drop the collection (if exists): `qdrant_service.client.delete_collection(collection_name)`
2. Run full rebuild script (above)
3. Verify with diagnostics endpoint: `GET /api/v1/qdrant-admin/stats`

### Scenario 2: Embedding Model Change

When upgrading embedding models (e.g., text-embedding-3-small → text-embedding-3-large):

1. Update `OPENAI_EMBEDDING_MODEL` and `OPENAI_EMBEDDING_DIMENSION` in config
2. Drop existing collection (vector dimensions changed)
3. Run full rebuild script
4. Update benchmark baselines

### Scenario 3: Single Document Needs Re-embedding

Use the single document procedure above, or:

```python
# Quick re-embed for one document
doc_id = UUID("...")
chunks = db.query(DocumentChunk).filter_by(document_id=doc_id).all()
texts = [c.content for c in chunks]
embeddings = embedding_service.generate_embeddings_batch(texts)
# ... upsert to Qdrant
```

---

## Verification Commands

```bash
# Check document/chunk counts
psql -c "SELECT COUNT(*) FROM documents WHERE embedded = true;"
psql -c "SELECT COUNT(*) FROM document_chunks WHERE embedding_id IS NOT NULL;"

# Check Qdrant collection stats
curl -X GET "http://localhost:8000/api/v1/qdrant-admin/stats" \
  -H "Authorization: Bearer $TOKEN"

# Verify parity
python scripts/verify_ingestion_parity.py
```

---

## Recommendations

### Immediate (Sprint 17)

1. ✅ Document current architecture (this file)
2. ⚠️ **Create `scripts/reprocess_embeddings.py`** with:
   - Batch processing with progress
   - Resume capability (track last processed doc)
   - Dry-run mode
   - Cost estimation output

### Near-term (Sprint 18-19)

3. Add `/api/v1/admin/reprocess-embeddings` endpoint
4. Add Qdrant health check to `/health` endpoint
5. Create runbook for embedding model upgrades

### Future (If Scale Demands)

6. Consider embedding storage in PostgreSQL (bytea or pgvector)
7. Evaluate Qdrant paid tier for backup features
8. Implement incremental reprocessing (only changed documents)

---

## Related Documentation

- [Qdrant Optimization Report](./qdrant-optimization.md) - HNSW tuning and benchmarks
- [Document Processing Pipeline](./document-processing.md) - Full ingestion flow
- [Ingestion Onboarding Runbook](./ingestion_onboarding_runbook.md) - Operational guide

---

*Last Updated: 2025-12-09*
*Mission: R17.2 - Qdrant Resilience & Reprocessing Strategy*
