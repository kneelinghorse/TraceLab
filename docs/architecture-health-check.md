# Architecture Health Check: Future-Proofing for Scale & Enhanced Search

**Mission**: R17.5
**Sprint**: 17
**Date**: 2025-12-09
**Status**: Complete

---

## Executive Summary

This investigation assesses TraceLab's schema architecture, index coverage, query patterns, and PEDR readiness. The goal is to ensure current decisions support future growth without introducing technical debt.

**Overall Health**: GOOD with minor gaps

| Area | Status | Notes |
|------|--------|-------|
| Index Coverage | ✅ Excellent | All key query paths indexed |
| PostgreSQL Features | ✅ Well-utilized | Full-text, JSONB, computed columns |
| Query Patterns | ⚠️ Minor concerns | Some N+1 risks in relationship loading |
| PEDR Readiness | ✅ Good foundation | Delta sync infrastructure exists |
| Metadata Completeness | ⚠️ Gaps identified | Missing audit fields on some entities |
| Brittleness Risks | ⚠️ Medium | CASCADE deletes addressed in R17.1 |

---

## 1. Index Audit

### 1.1 Complete Index Inventory

| Table | Index Name | Columns | Type | Purpose |
|-------|-----------|---------|------|---------|
| **documents** | `idx_documents_project_id` | `project_id` | B-tree | Project filtering |
| | `ix_documents_file_type` | `file_type` | B-tree | Faceted search |
| | `ix_documents_source_type` | `source_type` | B-tree | Faceted search |
| | `ix_documents_collection_date` | `collection_date` | B-tree | Date range filters |
| **document_chunks** | `idx_document_chunks_document_id` | `document_id` | B-tree | Document→chunk joins |
| | `idx_document_chunks_embedding_id` | `embedding_id` | B-tree | Qdrant ID lookups |
| | `ix_document_chunks_content_tsv` | `content_tsv` | **GIN** | Full-text search |
| | `uq_document_chunks_document_index` | `document_id, chunk_index` | Unique | Chunk ordering |
| **document_tags** | `ix_document_tags_tag_id` | `tag_id` | B-tree | Tag filtering |
| **insights** | `idx_insights_project_id` | `project_id` | B-tree | Project filtering |
| **insight_sources** | `idx_insight_sources_chunk_id` | `chunk_id` | B-tree | Chunk→insight joins |
| **missions** | `idx_missions_project_status` | `project_id, status` | Composite | Status filtering by project |
| | `idx_missions_mission_id` | `mission_id` | B-tree | Human ID lookup |
| | (implied) | `status` | B-tree | Status filtering |
| | (implied) | `deepsearch_job_id` | B-tree | Job tracking |
| **reports** | `ix_reports_project_id` | `project_id` | B-tree | Project filtering |
| | `ix_reports_status` | `status` | B-tree | Status filtering |
| | `ix_reports_created_at` | `created_at` | B-tree | Time ordering |
| **report_sources** | `ix_report_sources_report_id` | `report_id` | B-tree | Report→source joins |
| | `ix_report_sources_source_type_source_id` | `source_type, source_id` | Composite | Source lookups |
| **collections** | `ix_collections_created_at` | `created_at` | B-tree | Time ordering |
| **collection_items** | `ix_collection_items_collection_id` | `collection_id` | B-tree | Collection→item joins |
| | `ix_collection_items_chunk_id` | `chunk_id` | B-tree | Chunk→collection joins |
| | `uq_collection_item_collection_chunk` | `collection_id, chunk_id` | Unique | Deduplication |
| **search_history** | `ix_search_history_created_at` | `created_at` | B-tree | Time ordering |
| | `ix_search_history_query_mode` | `search_mode` | B-tree | Mode filtering |
| **saved_searches** | `ix_saved_searches_owner_created_at` | `owner, created_at` | Composite | User search lists |
| | `uq_saved_search_owner_name` | `owner, name` | Unique | Name uniqueness |
| **quality_checks** | `idx_quality_checks_entity` | `entity_type, entity_id` | Composite | Entity lookups |
| **api_keys** | `ix_api_keys_user_id` | `user_id` | B-tree | User filtering |
| | `ix_api_keys_key_prefix` | `key_prefix` | B-tree | Prefix lookups |
| **synthesis_cache** | `ix_synthesis_cache_input_hash` | `input_hash` | B-tree | Cache key lookup |

### 1.2 Index Assessment

**Strengths:**
- All foreign key columns are indexed
- Composite indexes exist for common filter combinations
- GIN index on TSVECTOR for full-text search
- Unique constraints prevent data integrity issues

**Potential Gaps:**

| Missing Index | Query Pattern | Impact | Recommendation |
|--------------|---------------|--------|----------------|
| `documents.uploaded_at` | Time-range queries | LOW | Add if date filtering common |
| `documents.processed` | Filter unprocessed docs | LOW | Add if admin dashboard needed |
| `tags.user_id` | User's tags list | LOW | Add when multi-user enabled |
| `missions.created_at` | Time ordering | MEDIUM | Add for mission history views |

**Recommendation**: Current indexes are sufficient. Add time-based indexes only if EXPLAIN ANALYZE shows sequential scans on production data.

---

## 2. Query Pattern Analysis

### 2.1 Common Query Patterns

| Pattern | Location | Indexed? | Notes |
|---------|----------|----------|-------|
| Documents by project | `app/api/v1/documents.py:70-91` | ✅ Yes | Uses `project_id` index |
| Chunks by document | `app/api/v1/documents.py:380-392` | ✅ Yes | Uses `document_id` index |
| Full-text search | `app/services/hybrid_search.py:197-257` | ✅ Yes | Uses GIN index |
| Missions by status | `app/services/pedr/delta_sync.py:152-161` | ✅ Yes | Uses composite index |
| Reports by project + status | `app/services/report_service.py` | ✅ Yes | Both indexed |

### 2.2 N+1 Query Risks

| Location | Pattern | Risk Level | Mitigation |
|----------|---------|------------|------------|
| `Document.chunks` relationship | Lazy loading | MEDIUM | Use `selectinload()` |
| `Report.sources` relationship | `lazy="selectin"` | ✅ Fixed | Pre-loaded |
| `Collection.items` relationship | `lazy="selectin"` | ✅ Fixed | Pre-loaded |
| `documents.py:287-296` | Chunk iteration for stats | LOW | In-memory after load |
| `preflight.py:240-253` | Join query | ✅ Fixed | Single query with joins |

**Current Good Patterns:**
- `Report.sources` uses `lazy="selectin"` (automatic batch loading)
- `Collection.items` uses `lazy="selectin"`
- `CollectionItem.chunk` uses `lazy="joined"` (single query)

**Recommendations:**
1. Add `selectinload(Document.chunks)` to document detail queries
2. Consider adding `with_loader_criteria()` for filtered relationship loading

### 2.3 Pagination Implementation

All list endpoints use cursor-based pagination with consistent patterns:
- `page` and `page_size` parameters
- Offset calculation: `(page - 1) * page_size`
- Total count query for pagination metadata
- Maximum page size limits (typically 100)

**Assessment**: ✅ Good - Consistent pagination prevents unbounded queries.

---

## 3. PostgreSQL Feature Usage

### 3.1 Full-Text Search (TSVECTOR)

**Implementation:**
```python
# app/models/chunk.py:18-22
content_tsv = Column(
    TSVector(),
    Computed("to_tsvector('english'::regconfig, coalesce(content, ''))", persisted=True),
    nullable=False
)
```

**Search execution:**
```python
# app/services/hybrid_search.py:213-214
ts_query = func.websearch_to_tsquery(self.keyword_language, query)
rank = func.ts_rank_cd(DocumentChunk.content_tsv, ts_query)
```

**Assessment**: ✅ Excellent
- Computed column auto-updates on content change
- GIN index enables fast FTS queries
- Uses `websearch_to_tsquery` for natural language queries
- `ts_rank_cd` provides relevance scoring

**Improvement Opportunities:**
- Consider `ts_headline()` for result highlighting
- Multi-language support (currently English only)

### 3.2 JSONB Usage

**Tables using JSONB:**

| Table | Column | Purpose | Queries? |
|-------|--------|---------|----------|
| `missions` | `success_criteria` | Array of strings | `jsonb_array_length()` |
| `missions` | `context` | Arbitrary metadata | Read-only |
| `missions` | `deliverables` | Array of strings | Read-only |
| `missions` | `research_phases` | Structured config | Read-only |
| `missions` | `tags` | Array of strings | Could be filtered |
| `missions` | `mission_metadata` | Extensible metadata | Read-only |
| `missions` | `execution_metadata` | Runtime metrics | Read-only |
| `missions` | `result_document_ids` | UUID array | Read-only |
| `missions` | `result_protocol` | Mission Protocol output | Read-only |
| `documents` | `document_metadata` | Provenance data | Read-only |
| `search_history` | `filters` | Search params | Read-only |
| `search_history` | `metadata_payload` | Extra data | Read-only |
| `search_history` | `top_chunks` | UUID array | Read-only |
| `quality_checks` | `details` | Check-specific data | Read-only |
| `quality_checks` | `recommendations` | Suggestion list | Read-only |
| `saved_searches` | `filters` | Search params | Read-only |
| `sync_state` | `sync_metadata` | Sync details | Read-only |
| `idempotency_records` | `response_data` | Cached response | Read-only |
| `synthesis_cache` | `citations` | Citation array | Read-only |

**Assessment**: ✅ Good
- JSONB used appropriately for schemaless metadata
- No JSONB field queries in hot paths (filters done in Python)
- `jsonb_array_length()` check on `success_criteria` is efficient

**Recommendation**: If JSONB tag filtering becomes common, add GIN index:
```sql
CREATE INDEX idx_missions_tags ON missions USING GIN (tags);
```

### 3.3 Computed Columns

| Table | Column | Expression | Benefit |
|-------|--------|------------|---------|
| `document_chunks` | `content_tsv` | `to_tsvector('english', content)` | Auto-maintained FTS |

**Assessment**: ✅ Excellent use of computed columns for derived data.

### 3.4 Check Constraints

| Table | Constraint | Expression |
|-------|-----------|------------|
| `projects` | `valid_research_type` | `research_type IN ('strategic', ...)` |
| `missions` | `success_criteria_not_empty` | `jsonb_array_length(success_criteria) > 0` |
| `missions` | `title_length` | `length(title) >= 3 AND length(title) <= 255` |
| `missions` | `valid_mission_status` | `status IN ('draft', 'queued', ...)` |

**Assessment**: ✅ Good data integrity at DB level.

---

## 4. PEDR Readiness Assessment

### 4.1 Current PEDR Infrastructure

**Available Services:**

| Service | Location | Purpose | Status |
|---------|----------|---------|--------|
| `DeltaSyncService` | `app/services/pedr/delta_sync.py` | Delta sync orchestration | ✅ Complete |
| `ManifestTransformer` | `app/services/pedr/manifest_transformer.py` | PEDR manifest generation | ✅ Complete |
| `QualityScoringService` | `app/services/pedr/quality_scoring.py` | Quality gate evaluation | ✅ Complete |
| `PreflightService` | `app/services/pedr/preflight.py` | Duplicate research check | ✅ Complete |
| `SyncEventEmitter` | `app/services/pedr/sync_events.py` | Event publication | ✅ Complete |

**Database Support:**

| Table | PEDR Purpose | Status |
|-------|-------------|--------|
| `sync_states` | Track last sync timestamp per entity | ✅ Complete |
| `missions` | Store mission protocol fields | ✅ Complete |
| `missions.deepsearch_job_id` | Link to DeepSearch jobs | ✅ Complete |
| `missions.result_protocol` | Store execution results | ✅ Complete |

### 4.2 What We Have for PEDR

1. **Delta Detection**: `updated_at` timestamps on all relevant tables
2. **Manifest Generation**: Transform TraceLab entities to PEDR URN format
3. **Quality Gates**: 5-gate quality scoring system
4. **Preflight Queries**: Check existing research before launching new missions
5. **Sync State Persistence**: Track per-entity sync cursors

### 4.3 What PEDR Integration Would Require

| Requirement | Current State | Gap? |
|-------------|--------------|------|
| HTTP client for PEDR API | Not implemented | YES - needs `PEDRClient` class |
| Authentication tokens | Not implemented | YES - needs credential management |
| Bidirectional sync | Outbound only | YES - needs inbound handler |
| Conflict resolution | Not designed | YES - needs merge strategy |
| Webhook receiver | Not implemented | YES - for PEDR→TraceLab events |

### 4.4 PEDR Readiness Checklist

| Item | Status | Notes |
|------|--------|-------|
| Mission schema compatible | ✅ Yes | Mission Protocol fields present |
| Quality gates tracked | ✅ Yes | `quality_scoring.py` handles this |
| Delta sync infrastructure | ✅ Yes | Ready to plug in HTTP client |
| Preflight queries | ✅ Yes | Semantic similarity + quality filtering |
| API authentication | ⚠️ Partial | API keys exist, PEDR auth not integrated |
| PEDR HTTP client | ❌ No | Needs implementation |
| Bidirectional sync | ❌ No | Not designed yet |

**Assessment**: TraceLab is **70% ready** for PEDR integration. The internal infrastructure exists; what's missing is the actual PEDR HTTP client and bidirectional sync logic.

---

## 5. Metadata Completeness Assessment

### 5.1 Standard Metadata Fields Audit

| Table | `created_at` | `updated_at` | `created_by` | Notes |
|-------|-------------|-------------|--------------|-------|
| `projects` | ✅ | ✅ | ❌ | Missing creator tracking |
| `documents` | ✅ (`uploaded_at`) | ❌ | ❌ | No `updated_at` |
| `document_chunks` | ✅ | ❌ | - | No `updated_at` (immutable) |
| `insights` | ✅ | ✅ | ✅ | Complete |
| `missions` | ✅ | ✅ | ✅ | Complete |
| `reports` | ✅ | ✅ | ❌ | Missing creator |
| `collections` | ✅ | ✅ | ❌ | Missing creator |
| `tags` | ❌ | ❌ | ❌ | No timestamps |
| `search_history` | ✅ | ✅ | ❌ | `user_label` exists |
| `saved_searches` | ✅ | ✅ | ✅ (`owner`) | Complete |
| `api_keys` | ✅ | ❌ (`last_used_at`) | - | Usage tracked |
| `quality_checks` | ✅ (`performed_at`) | ❌ | ✅ (`performed_by`) | Audit complete |
| `sync_states` | ✅ | ✅ | - | System table |

### 5.2 Metadata Gaps

**High Priority:**

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| `documents.updated_at` | Can't track document modifications | Add column with trigger |
| `projects.created_by` | No ownership tracking | Add when auth matures |
| `reports.created_by` | Can't audit report creators | Add column |
| `tags.created_at` | Can't track tag age | Add timestamps |

**Low Priority:**

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| `collections.created_by` | No ownership | Add when needed |
| `document_chunks.updated_at` | Chunks are immutable | Not needed |

### 5.3 Provenance Metadata

| Entity | Source Tracking | Quality Tracking | Version Tracking |
|--------|----------------|------------------|------------------|
| Documents | `source_type`, `document_metadata` | `validation_status`, `transcription_accuracy` | ❌ No versioning |
| Chunks | `embedding_id` (Qdrant link) | Quality via parent doc | ❌ No versioning |
| Insights | `created_by`, `sources` relation | `validated`, `validation_date` | ❌ No versioning |
| Reports | `sources` relation | `status` | `version`, `parent_id` ✅ |
| Missions | `created_by`, `result_document_ids` | Quality gates in JSONB | ❌ No versioning |

**Assessment**: Reports have the best provenance model with versioning and parent links. Other entities could benefit from similar patterns.

---

## 6. Brittleness Risk Assessment

### 6.1 CASCADE DELETE Risks

*Addressed in R17.1 Data Protection Audit*

**Summary**: Project deletion cascades through documents, chunks, insights, and missions. Single API call can destroy entire research repository.

**Status**: Recommendations in R17.1:
- [ ] Add authentication to project/document DELETE (P0)
- [ ] Add confirmation parameter (P1)
- [ ] Implement soft delete (P1)

### 6.2 Qdrant Synchronization Risks

*Addressed in R17.2 Qdrant Resilience*

**Risk**: PostgreSQL and Qdrant can diverge:
- Delete chunk from PostgreSQL → Qdrant orphan
- Qdrant data loss → No automatic recovery

**Mitigation**: PostgreSQL is source of truth. Qdrant can be rebuilt from chunks.

### 6.3 Schema Evolution Risks

*Addressed in R17.4 Schema Evolution Guide*

**Risk**: Some migrations lack proper `downgrade()` functions.

**Mitigation**: Follow migration best practices in `docs/schema-evolution-guide.md`.

### 6.4 Additional Brittleness Concerns

| Risk | Severity | Mitigation |
|------|----------|------------|
| Single Qdrant collection | MEDIUM | Collection name in config; no multi-tenant isolation |
| No database connection pooling config | LOW | SQLAlchemy defaults usually sufficient |
| Embedding model lock-in | LOW | Can re-embed; see R17.2 procedures |
| API key single-use model | LOW | Can rotate; short expiry optional |

---

## 7. Cross-System Sync Considerations

### 7.1 TraceLab ↔ DeepSearch Sync

**Current State:**
- DeepSearch can submit missions to TraceLab via API
- TraceLab can export to PEDR format (outbound)
- No bidirectional sync implemented

**Sync Architecture Options:**

| Pattern | Pros | Cons | Recommendation |
|---------|------|------|----------------|
| **Event-driven** | Real-time, decoupled | Complexity, ordering | ✅ Preferred |
| **Polling** | Simple | Latency, load | For fallback only |
| **Shared DB** | Consistent | Tight coupling | ❌ Avoid |

**Recommended Approach:**
1. TraceLab publishes events on mission/document changes
2. DeepSearch subscribes to events via webhook
3. Delta sync for bulk reconciliation
4. Idempotency keys prevent duplicates

### 7.2 Data Consistency Model

| Entity | Consistency Requirement | Approach |
|--------|------------------------|----------|
| Missions | Eventual | Last-write-wins with conflict detection |
| Documents | Strong | TraceLab is authoritative |
| Search Results | Eventual | Cache invalidation on change |

---

## 8. Recommendations Summary

### 8.1 Immediate (No Migration Needed)

| Action | Effort | Impact |
|--------|--------|--------|
| Add `selectinload()` to document queries | 1 hour | Performance |
| Document PEDR integration requirements | 2 hours | Clarity |
| Add missing logging for sync operations | 2 hours | Observability |

### 8.2 Near-Term (Migration Required)

| Action | Effort | Impact |
|--------|--------|--------|
| Add `documents.updated_at` column | 1 hour | Audit trail |
| Add `reports.created_by` column | 30 min | Audit trail |
| Add `tags` timestamps | 30 min | Data hygiene |
| Add `missions.created_at` index | 10 min | Query performance |

### 8.3 Future (When Scaling)

| Action | Trigger | Effort |
|--------|---------|--------|
| Add GIN index on `missions.tags` | When tag filtering used | 30 min |
| Implement PEDR HTTP client | When PEDR integration approved | 2-3 days |
| Add multi-language FTS | When non-English content needed | 1 day |
| Implement soft delete | Per R17.1 recommendations | 4-8 hours |

---

## 9. Architecture Health Scorecard

| Dimension | Score | Notes |
|-----------|-------|-------|
| **Index Coverage** | 9/10 | Comprehensive; minor gaps for future |
| **PostgreSQL Features** | 9/10 | Excellent use of TSVECTOR, JSONB, computed columns |
| **Query Patterns** | 8/10 | Good; some N+1 risks in relationship loading |
| **Data Integrity** | 8/10 | Check constraints good; CASCADE risks noted |
| **Audit Trail** | 7/10 | Missing `updated_at`/`created_by` on some tables |
| **PEDR Readiness** | 7/10 | Infrastructure ready; client not implemented |
| **Scalability** | 8/10 | Good foundation; monitor as data grows |
| **Resilience** | 7/10 | Qdrant rebuildable; soft delete needed |

**Overall**: 8/10 - Solid architecture with room for improvement

---

## 10. References

- R17.1: [Data Protection Audit](./data-protection-audit.md)
- R17.2: [Qdrant Resilience](./qdrant-resilience.md)
- R17.3: [Report Metadata Analysis](./report-metadata-analysis.md)
- R17.4: [Schema Evolution Guide](./schema-evolution-guide.md)
- [Database Optimization](./database-optimization.md)
- [Qdrant Optimization](./qdrant-optimization.md)

---

*Last Updated: 2025-12-09*
*Mission: R17.5 - Future-Proofing for Scale & Enhanced Search*
