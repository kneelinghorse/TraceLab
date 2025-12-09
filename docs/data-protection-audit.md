# Data Protection & Recovery Patterns Audit

**Date**: 2025-12-09
**Sprint**: 17
**Mission**: R17.1
**Status**: Complete

## Executive Summary

This audit examines TraceLab's current data protection mechanisms, CASCADE behaviors, and recovery capabilities. Key findings include aggressive CASCADE DELETE usage that creates risk of accidental bulk data loss, and several recommendations for improved safeguards.

**Risk Level**: MEDIUM-HIGH
**Critical Gaps Identified**: 3

---

## 1. Foreign Key Relationship Audit

### 1.1 Complete FK Cascade Matrix

| Parent Table | Child Table | FK Column | ON DELETE | Risk Level |
|--------------|-------------|-----------|-----------|------------|
| `projects` | `documents` | `project_id` | **CASCADE** | HIGH |
| `projects` | `insights` | `project_id` | **CASCADE** | HIGH |
| `projects` | `missions` | `project_id` | **CASCADE** | HIGH |
| `projects` | `reports` | `project_id` | SET NULL | LOW |
| `documents` | `document_chunks` | `document_id` | **CASCADE** | HIGH |
| `documents` | `document_tags` | `document_id` | **CASCADE** | LOW |
| `documents` | `document_processing_statuses` | `document_id` | **CASCADE** | LOW |
| `documents` | `ingestion_jobs` | `document_id` | **CASCADE** | LOW |
| `document_chunks` | `collection_items` | `chunk_id` | **CASCADE** | MEDIUM |
| `document_chunks` | `insight_sources` | `chunk_id` | **CASCADE** | MEDIUM |
| `document_chunks` | `document_chunks` (prev) | `prev_chunk_id` | RESTRICT* | LOW |
| `document_chunks` | `document_chunks` (next) | `next_chunk_id` | RESTRICT* | LOW |
| `tags` | `document_tags` | `tag_id` | **CASCADE** | LOW |
| `tags` | `tags` (parent) | `parent_id` | RESTRICT* | LOW |
| `insights` | `insight_sources` | `insight_id` | **CASCADE** | LOW |
| `collections` | `collection_items` | `collection_id` | **CASCADE** | LOW |
| `reports` | `report_sources` | `report_id` | **CASCADE** | LOW |
| `reports` | `reports` (parent) | `parent_id` | SET NULL | LOW |
| `reports` | `missions` (result) | `result_report_id` | SET NULL | LOW |

*\*RESTRICT is PostgreSQL default when ON DELETE not specified*

### 1.2 Cascade Chain Analysis

#### Critical Cascade Path: Project Deletion

```
DELETE projects.id = X
    └── CASCADE → documents (all project documents)
            └── CASCADE → document_chunks (all chunks)
                    └── CASCADE → collection_items (breaks collections)
                    └── CASCADE → insight_sources (breaks insights)
            └── CASCADE → document_tags
            └── CASCADE → document_processing_statuses
            └── CASCADE → ingestion_jobs
    └── CASCADE → insights (all project insights)
            └── CASCADE → insight_sources
    └── CASCADE → missions (all project missions)
    └── SET NULL → reports.project_id (preserves reports)
```

**Impact**: A single `DELETE /api/v1/projects/{id}` call will:
- Delete ALL documents in that project
- Delete ALL chunks from those documents
- Delete ALL insights derived from that project
- Delete ALL missions associated with that project
- Remove items from collections (orphaning collection structures)
- Break citation links in existing reports

#### Moderate Cascade Path: Document Deletion

```
DELETE documents.id = X
    └── CASCADE → document_chunks (all chunks)
            └── CASCADE → collection_items
            └── CASCADE → insight_sources
    └── CASCADE → document_tags
    └── CASCADE → document_processing_statuses
    └── CASCADE → ingestion_jobs
```

**Impact**: Deleting a document removes all its chunks and breaks:
- Collection items referencing those chunks
- Insight sources referencing those chunks

---

## 2. API DELETE Endpoint Audit

### 2.1 Current DELETE Endpoints

| Endpoint | Auth Required | Confirmation | Bulk Safe | Risk |
|----------|---------------|--------------|-----------|------|
| `DELETE /api/v1/projects/{id}` | No* | None | No | **CRITICAL** |
| `DELETE /api/v1/documents/{id}` | No* | None | No | HIGH |
| `DELETE /api/v1/missions/{id}` | No | None | Yes | LOW |
| `DELETE /api/v1/reports/{id}` | Yes | None | Yes | LOW |
| `DELETE /api/v1/collections/{id}` | Yes | None | Yes | LOW |
| `DELETE /api/v1/collections/{id}/chunks/{id}` | Yes | None | Yes | LOW |
| `DELETE /api/v1/api-keys/{id}` | Yes | None | Yes | LOW |
| `DELETE /api/v1/search/history` | Yes | None | Yes (bulk) | LOW |
| `DELETE /api/v1/saved-searches/{id}` | Yes | None | Yes | LOW |
| `DELETE /api/v1/corrections/completed` | Yes | None | Yes | LOW |

*\*Uses `get_db` dependency only, no auth middleware*

### 2.2 Critical Vulnerabilities

1. **Project DELETE has no authentication** - Anyone with API access can delete entire projects
2. **Document DELETE has no authentication** - Anyone can delete documents
3. **No confirmation mechanism** - All deletes are immediate
4. **No soft delete** - All deletes are permanent (hard delete)

---

## 3. Backup Configuration

### 3.1 Current State

**PostgreSQL (Railway)**:
- Railway provides automatic daily backups for Pro plans
- Retention: 7 days (default)
- Point-in-time recovery: Available on Pro plans

**Qdrant (Vector Database)**:
- No documented backup procedure
- Snapshots possible via Qdrant API but not automated
- Risk: Vector embeddings lost if Qdrant data corrupted

### 3.2 Backup Gaps

| Component | Automated Backup | Manual Backup Procedure | Recovery Tested |
|-----------|-----------------|------------------------|-----------------|
| PostgreSQL | Yes (Railway) | Not documented | No |
| Qdrant | **No** | **Not documented** | **No** |
| File uploads | **No** | **Not documented** | **No** |

---

## 4. Recovery Runbook

### 4.1 Scenario: Accidental Project Deletion

**Symptoms**: User reports project and all documents gone

**Recovery Steps**:

1. **Identify deletion time** from Railway logs or application logs
2. **Railway Console** → Database → Backups → Select backup before deletion
3. **Restore to new database**:
   ```bash
   # Export from backup
   pg_dump -h backup-host -U user -d tracelab > backup.sql
   # Restore to production (careful!)
   psql -h prod-host -U user -d tracelab < backup.sql
   ```
4. **Qdrant recovery**: Re-embed all chunks from restored documents
   ```bash
   curl -X POST "$API_URL/api/v1/admin/reindex-embeddings" \
     -H "Authorization: Bearer $TOKEN"
   ```
5. **Verify**: Check document counts, chunk counts, search functionality

**Estimated Recovery Time**: 1-4 hours depending on data volume

### 4.2 Scenario: Accidental Document Deletion

**Symptoms**: Single document missing

**Recovery Steps**:

1. If within same day: Contact Railway support for point-in-time recovery
2. If older: Restore from daily backup (see 4.1)
3. Re-embed chunks for restored document

### 4.3 Scenario: Qdrant Data Loss

**Symptoms**: Search returns no results, embeddings missing

**Recovery Steps**:

1. **Re-initialize collection**:
   ```bash
   curl -X POST "$API_URL/api/v1/admin/init-qdrant" \
     -H "Authorization: Bearer $TOKEN"
   ```
2. **Re-embed all chunks**:
   ```bash
   # This endpoint needs to be implemented
   curl -X POST "$API_URL/api/v1/admin/reindex-all-embeddings" \
     -H "Authorization: Bearer $TOKEN"
   ```
3. **Verify**: Run search tests

**Estimated Recovery Time**: 2-8 hours depending on chunk count

---

## 5. Soft Delete Recommendation

### 5.1 Decision: YES - Implement Soft Deletes

**Rationale**:
- CASCADE DELETEs are too aggressive for a research platform
- User data (research documents, insights) is irreplaceable
- Recovery from backup is slow and risky
- Soft delete enables "undo" functionality

### 5.2 Recommended Implementation

**Tables requiring soft delete**:
- `projects` (HIGH priority)
- `documents` (HIGH priority)
- `insights` (MEDIUM priority)
- `reports` (LOW priority - already SET NULL protected)

**Schema changes**:
```python
# Add to affected models
deleted_at = Column(DateTime, nullable=True, index=True)
deleted_by = Column(String, nullable=True)
```

**Query pattern**:
```python
# All queries should filter
session.query(Project).filter(Project.deleted_at.is_(None))
```

**Purge policy**:
- Soft-deleted records purged after 30 days
- Scheduled job to hard-delete old records

---

## 6. Recommended Safeguards

### 6.1 Immediate Actions (Sprint 17-18)

| Priority | Action | Effort |
|----------|--------|--------|
| P0 | Add authentication to project DELETE endpoint | 1 hour |
| P0 | Add authentication to document DELETE endpoint | 1 hour |
| P1 | Add confirmation parameter for project DELETE | 2 hours |
| P1 | Implement soft delete for projects | 4 hours |
| P1 | Implement soft delete for documents | 4 hours |

### 6.2 API Confirmation Pattern

```python
@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: UUID,
    confirm: bool = Query(False, description="Must be true to delete"),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> None:
    """Delete a project. Requires confirm=true."""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Project deletion requires confirm=true query parameter"
        )
    # ... proceed with delete
```

### 6.3 Backup Improvements

| Action | Timeline | Owner |
|--------|----------|-------|
| Document Railway backup procedure | Sprint 17 | DevOps |
| Implement Qdrant snapshot automation | Sprint 18 | Backend |
| Test full recovery procedure | Sprint 18 | QA |
| Set up backup monitoring alerts | Sprint 18 | DevOps |

---

## 7. Orphan Record Analysis

### 7.1 Current Orphan Risks

| Scenario | Orphan Type | Impact |
|----------|-------------|--------|
| Delete document with chunks in collections | `collection_items` with invalid `chunk_id` | **Fixed by CASCADE** |
| Delete chunk referenced by insight | `insight_sources` with invalid `chunk_id` | **Fixed by CASCADE** |
| Delete project with reports | Reports with NULL `project_id` | **Acceptable (SET NULL)** |

### 7.2 Potential Orphans

The current CASCADE configuration prevents most orphans. However:

- **Qdrant orphans**: Deleting chunks from PostgreSQL does NOT delete vectors from Qdrant
- **File orphans**: Deleting documents may leave orphaned files on disk (partially handled in code)

**Recommendation**: Implement cleanup jobs:
```python
# Qdrant orphan cleanup
async def cleanup_orphan_vectors():
    """Delete Qdrant vectors with no matching PostgreSQL chunk."""
    pass

# File orphan cleanup
async def cleanup_orphan_files():
    """Delete files with no matching document record."""
    pass
```

---

## 8. Summary & Next Steps

### Critical Findings

1. **Project DELETE is unauthenticated** - CRITICAL security issue
2. **No soft delete** - Data loss is permanent
3. **Qdrant backups not automated** - Vector data at risk

### Recommended Sprint 17-18 Work

1. [ ] Add auth to project/document DELETE endpoints (P0)
2. [ ] Add confirmation parameter for destructive operations (P1)
3. [ ] Implement soft delete for projects and documents (P1)
4. [ ] Document backup procedures (P1)
5. [ ] Automate Qdrant snapshots (P2)
6. [ ] Test full recovery scenario (P2)

### Success Metrics

- Zero unauthenticated DELETE endpoints
- Soft delete coverage for high-value tables
- Documented and tested recovery procedure
- <4 hour recovery time objective (RTO)

---

*Audit conducted as part of Sprint 17 research mission R17.1*
