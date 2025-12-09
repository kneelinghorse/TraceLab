# Schema Evolution & Migration Guide

TraceLab uses **Alembic** for PostgreSQL schema management and **Qdrant** for vector storage.
This guide documents our practices, procedures, and quality standards for evolving these schemas.

---

## Table of Contents

1. [Migration Inventory](#migration-inventory)
2. [Current Patterns & Practices](#current-patterns--practices)
3. [Migration Best Practices Checklist](#migration-best-practices-checklist)
4. [Breaking Change Handling](#breaking-change-handling)
5. [Rollback Procedures](#rollback-procedures)
6. [Testing Requirements](#testing-requirements)
7. [Coordination Checklist (Postgres + Qdrant + API)](#coordination-checklist)
8. [Migration Template](#migration-template)
9. [Known Gaps & Recommendations](#known-gaps--recommendations)

---

## Migration Inventory

As of Sprint 17, TraceLab has **17 Alembic migrations**:

| Revision | Name | Type | Reversible |
|----------|------|------|------------|
| 001_initial | Initial schema | Create tables | Yes |
| 002_processing_status | Document processing audit | Create table | Yes |
| 003_onboarding_api | Onboarding API support | Add columns | Yes |
| 004_mission_protocol | Mission protocol validation | Add columns | Yes |
| 005_performance_indexes | Performance indexes | Create indexes | Yes |
| 006_add_fulltext_search | PostgreSQL TSVECTOR | Add computed column | Yes |
| 007_faceted_filter_indexes | Filter indexes | Create indexes | Yes |
| 008_search_history | Search history table | Create table | Yes |
| 009_saved_searches | Saved searches table | Create table | Yes |
| 010_evidence_linking | Evidence linking metadata | Add column | Yes |
| 011_add_collections | Collections & items | Create tables | Yes |
| 012_add_api_keys | API keys table | Create table | Yes |
| 013_add_reports | Reports & synthesis cache | Create tables | Yes |
| 014_missions_revamp | Missions schema overhaul | **Breaking** | Partial |
| 015_document_metadata | Document metadata column | Add column | No downgrade |
| 016_repair_missions | Repair schema (idempotent) | Create if missing | No downgrade |
| 017_fix_reports_schema | Reports schema fix | Add columns | No downgrade |

### Migration Categories

- **Additive** (Safe): 001-013 - Add tables/columns/indexes without altering existing data
- **Transformative** (Risky): 014 - Data migration with column drops and constraint changes
- **Repair** (Idempotent): 016-017 - Schema repair for corrupted state recovery

---

## Current Patterns & Practices

### Strengths Observed

1. **Idempotent Checks**: Recent migrations use `inspector.has_table()` and column existence checks:
   ```python
   if not inspector.has_table("reports"):
       op.create_table(...)
   ```

2. **Dialect Detection**: Migrations handle PostgreSQL vs SQLite differences:
   ```python
   is_pg = bind.dialect.name == "postgresql"
   postgresql.JSONB() if is_pg else sa.JSON()
   ```

3. **Cascade Deletes**: Foreign keys use `ondelete="CASCADE"` or `ondelete="SET NULL"` appropriately

4. **Index Creation**: Migrations create indexes for common query patterns

5. **Server Defaults**: Columns use `server_default` for new rows

### Patterns to Improve

1. **Downgrade Functions**: Later migrations have `pass` or incomplete downgrades
2. **No Migration Testing**: No CI pipeline for testing migrations
3. **No Dry-Run Mode**: Migrations run directly in production on deploy
4. **Manual Repair Scripts**: 016/017 exist because of schema corruption issues

---

## Migration Best Practices Checklist

Use this checklist when writing new migrations:

### Pre-Migration

- [ ] Review affected models in `app/models/`
- [ ] Check for dependent foreign keys
- [ ] Identify Qdrant payload schema changes (if vector metadata affected)
- [ ] Plan for NULL handling on existing rows
- [ ] Document the migration purpose in docstring

### Migration Code

- [ ] Use idempotent checks (`inspector.has_table()`, column checks)
- [ ] Handle both PostgreSQL and SQLite if supporting both
- [ ] Add `server_default` for new required columns
- [ ] Create indexes for filterable/sortable columns
- [ ] Use explicit revision IDs (e.g., `017_feature_name`)
- [ ] Include complete `downgrade()` function

### Data Migration

- [ ] Backfill NULL values before adding NOT NULL constraint
- [ ] Handle duplicates before adding UNIQUE constraint
- [ ] Use batch updates for large tables
- [ ] Preserve existing data during column renames

### Post-Migration

- [ ] Run `alembic upgrade head` locally
- [ ] Run `alembic downgrade -1` and `upgrade head` to test reversibility
- [ ] Update affected Pydantic schemas in `app/schemas/`
- [ ] Update API endpoint documentation
- [ ] Add/update model tests

---

## Breaking Change Handling

### Definition of Breaking Changes

1. **Column Removal**: Dropping columns with data
2. **Type Changes**: Changing column types (especially narrowing)
3. **Constraint Addition**: Adding NOT NULL or UNIQUE to existing columns
4. **Enum Changes**: Removing values from CHECK constraints
5. **Index Changes**: Removing indexes that queries depend on

### Breaking Change Procedure

**Phase 1: Prepare (Deploy N)**
```python
# Add new column alongside old
op.add_column("missions", sa.Column("mission_id_new", ...))

# Copy data
op.execute("UPDATE missions SET mission_id_new = mission_id")
```

**Phase 2: Migrate (Deploy N+1)**
```python
# Application now reads from new column
# Verify all data migrated correctly
```

**Phase 3: Cleanup (Deploy N+2)**
```python
# Drop old column after verification
op.drop_column("missions", "mission_id_old")
```

### Example: Mission Schema Revamp (014)

Migration 014 demonstrates a single-deploy breaking change:

1. Detect old schema: `has_old_schema = "mission_data" in existing_columns`
2. Add new columns with NULL allowed
3. Data migration: Extract from JSON blob to new columns
4. Drop old columns: `op.drop_column("missions", "mission_data")`
5. Add constraints: NOT NULL, CHECK, UNIQUE

**Risks of this approach:**
- No rollback path once old columns dropped
- Data loss if migration fails mid-way
- Downtime during migration

**Recommended alternative:** Three-phase deploy for production systems.

---

## Rollback Procedures

### When Rollback is Possible

Rollback is safe when:
- Only indexes/constraints added
- Only new tables added (no data in them)
- New columns added with defaults
- No data migration occurred

### Rollback Command

```bash
# Rollback one migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade 016_repair_missions

# View current state
alembic current
alembic history
```

### When Rollback is NOT Possible

1. **Migrations 015-017**: `downgrade()` is `pass` - no rollback
2. **Post-data-migration**: 014 after data extracted from JSON blob
3. **After column drops**: Original data is gone

### Emergency Recovery

If a migration fails mid-way:

1. **Check current state**:
   ```bash
   alembic current
   ```

2. **Manual inspection**:
   ```sql
   SELECT * FROM alembic_version;
   \d+ table_name
   ```

3. **Manual repair options**:
   - Fix and re-run migration
   - Stamp database to skip broken migration: `alembic stamp <revision>`
   - Restore from backup (preferred)

### Railway Deployment Behavior

Current `railway.json`:
```json
{
  "deploy": {
    "startCommand": "bash -lc \"alembic upgrade head && uvicorn app.main:app ...\""
  }
}
```

**Risk**: If migration fails, service won't start. Railway will retry up to 10 times.

**Recommendation**: Add migration verification step before uvicorn starts.

---

## Testing Requirements

### Local Testing

Before committing a migration:

```bash
# Fresh database
dropdb tracelab_test && createdb tracelab_test
alembic upgrade head
alembic downgrade base  # Test full downgrade path
alembic upgrade head    # Verify clean re-upgrade

# Incremental
alembic downgrade -1
alembic upgrade head
```

### CI Testing (Recommended - Not Currently Implemented)

```yaml
# .github/workflows/test-migrations.yml
jobs:
  migrations:
    services:
      postgres:
        image: postgres:15
    steps:
      - run: alembic upgrade head
      - run: alembic downgrade -1
      - run: alembic upgrade head
      - run: python -m pytest tests/test_models.py
```

### Model Tests

After migration, verify:
- Model instantiation
- CRUD operations
- Relationship loading
- JSON field serialization

---

## Coordination Checklist

### PostgreSQL + Qdrant + API Changes

When changes affect multiple systems:

#### 1. Qdrant Payload Schema

Qdrant payloads currently include:
- `content` (text)
- `document_id` (UUID string)
- `project_id` (UUID string)
- `chunk_index` (int)
- `source_type` (string, optional)

**If adding payload fields:**
- Update `QdrantService.upsert_chunks()`
- Update `QdrantService.search_chunks()` to return new fields
- Consider adding payload index: `_create_payload_indexes()`
- Update API schemas

#### 2. Database + API Coordination

```
1. Database migration (alembic)
   ↓
2. Model update (app/models/)
   ↓
3. Service update (app/services/)
   ↓
4. Schema update (app/schemas/)
   ↓
5. API endpoint update (app/api/v1/)
   ↓
6. Frontend update (if applicable)
```

#### 3. Version Checklist

- [ ] Database schema version matches model definitions
- [ ] API response schemas include new fields
- [ ] Qdrant payload schema documented
- [ ] Frontend types updated (if TypeScript)

---

## Migration Template

Use this template for new migrations:

```python
"""Add [feature] - [brief description].

Revision ID: 018_feature_name
Revises: 017_fix_reports_schema
Create Date: YYYY-MM-DD HH:MM:SS.000000

Purpose:
    [Describe what this migration adds/changes and why]

Breaking Changes:
    [List any breaking changes, or "None"]

Rollback Notes:
    [Describe rollback procedure, or "Safe to rollback"]
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "018_feature_name"
down_revision = "017_fix_reports_schema"
branch_labels = None
depends_on = None


def is_postgresql(bind) -> bool:
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    is_pg = is_postgresql(bind)

    # Idempotent check
    if not inspector.has_table("new_table"):
        op.create_table(
            "new_table",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True) if is_pg else sa.String(36),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()") if is_pg else None,
            ),
            # ... columns
        )
        op.create_index("ix_new_table_field", "new_table", ["field"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table("new_table"):
        op.drop_index("ix_new_table_field", table_name="new_table")
        op.drop_table("new_table")
```

---

## Known Gaps & Recommendations

### Current Gaps

| Gap | Risk | Recommendation |
|-----|------|----------------|
| No CI migration testing | High | Add `test-migrations.yml` workflow |
| Incomplete downgrades | Medium | Write proper `downgrade()` for 015-017 |
| No backup before migration | High | Add pg_dump step to deploy |
| No dry-run mode | Medium | Implement `--sql` mode review |
| No schema versioning API | Low | Add `/health/schema` endpoint |
| Qdrant schema undocumented | Medium | Add `docs/qdrant-schema.md` |

### Priority Actions

1. **Immediate**: Document Qdrant payload schema
2. **Sprint 18**: Add CI migration testing
3. **Sprint 18**: Add database backup to deploy process
4. **Future**: Implement three-phase deploy for breaking changes

### Schema Version Endpoint (Recommended)

```python
@router.get("/health/schema")
async def schema_health():
    return {
        "alembic_version": get_current_revision(),
        "expected_version": "017_fix_reports_schema",
        "qdrant_collection": settings.qdrant_collection_name,
        "status": "healthy"
    }
```

---

## References

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- Internal: `docs/qdrant-optimization.md`
- Internal: `docs/qdrant-railway-setup.md`

---

*Last Updated: Sprint 17*
*Author: Research Mission R17.4*
