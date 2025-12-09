# Report Metadata Extraction Analysis

**Mission:** R17.3
**Status:** Completed
**Date:** 2025-12-09

## Executive Summary

This analysis examines what structured metadata exists in TraceLab synthesized reports and evaluates whether extracting and storing this metadata would provide meaningful value for enhanced searchability and future knowledge graph capabilities.

**Recommendation:** **NOT NOW** - Focus on vector search improvements first. The current citation-based source tracking (`ReportSource` model) provides sufficient traceability. Report metadata extraction offers marginal benefits that don't justify the implementation complexity at this stage.

## Analysis Scope

### Investigation Areas

1. Synthesis service report generation (`app/services/synthesis.py`)
2. Report models and schemas (`app/models/report.py`, `app/schemas/report.py`)
3. Auto-report generation from DeepSearch (`app/services/auto_report.py`)
4. Report export service (`app/services/report_export.py`)
5. Chunking approach (`app/services/chunking.py`)

### Questions Addressed

- What metadata exists in typical reports?
- What formats do citations/references take?
- Are there consistent patterns we can parse?
- What would we do with extracted metadata?
- How does this feed into enhanced search?
- What's the ROI of extraction vs. just vector search?
- Would this require schema changes?

## Current Report Architecture

### Report Model Structure

Reports in TraceLab are stored with the following schema (`app/models/report.py:14-49`):

| Field | Type | Purpose |
|-------|------|---------|
| `id` | UUID | Primary key |
| `project_id` | UUID (nullable) | Project association |
| `title` | String(255) | Report title |
| `report_type` | String(50) | `summary`, `report`, `bullets`, `markdown` |
| `prompt` | Text (nullable) | Custom synthesis prompt used |
| `content` | Text | Full report content (markdown) |
| `content_hash` | String(64) | SHA-256 for deduplication |
| `version` | Integer | Version tracking |
| `parent_id` | UUID (nullable) | Report lineage |
| `status` | String(20) | `draft` or `final` |
| `tokens_used` | Integer | LLM token consumption |
| `chunk_count` | Integer | Source chunk count |

### Source Tracking (ReportSource)

The `ReportSource` model (`app/models/report.py:52-70`) already tracks:

- `source_type`: `'collection'` or `'chunk'`
- `source_id`: UUID of the source entity
- Timestamp of when source was added

**This provides existing provenance tracking** - we know which chunks/collections contributed to each report.

### Citation Format in Reports

The synthesis service (`app/services/synthesis.py:343-376`) generates reports with:

1. **Numbered markers** in context: `[1]`, `[2]`, etc.
2. **Citation map** tracking each marker to:
   - `chunk_id`: Source chunk UUID
   - `document_id`: Parent document UUID
   - `excerpt`: First 100 chars of chunk content

The LLM output includes inline citations like `[1][3]` which are post-processed to extract which sources were actually used.

## Metadata Patterns Analysis

### Synthesis-Generated Reports

Reports generated via `/api/v1/synthesize` contain:

1. **Structured prose** with inline citation markers `[1]`, `[2]`
2. **No headers** in summary format
3. **Section headers** in report format (e.g., "Executive Summary", topic sections)
4. **Bullet points** in bullets format

Citation patterns:
```
This is a key finding [1]. Multiple sources support this [2][3].
```

### Auto-Generated Reports (DeepSearch)

Reports from DeepSearch missions (`app/services/auto_report.py:27-134`) have more predictable structure:

```markdown
# Research: {mission_title}

## Summary
{synthesis text}

### Key Findings
- Finding 1
- Finding 2

## Findings
### {Finding Title}
*Confidence: 85%*
{description}

## Sources
- [Title](URL) *(relevance: 90%)*

## Quality Checkpoints
- [x] Checkpoint passed
```

### Potential Extractable Metadata

| Metadata Type | Source | Extraction Difficulty | Value |
|--------------|--------|----------------------|-------|
| External URLs | Report content | Low (regex) | Medium |
| Citation markers `[1]` | Report content | Low (regex) | Already tracked |
| Section headings | Report content | Medium (markdown parse) | Low |
| Confidence scores | DeepSearch protocol | Low (structured) | Medium |
| Key findings | DeepSearch protocol | Low (structured) | Medium |
| Quality checkpoints | DeepSearch protocol | Low (structured) | Low |
| Entities (people, orgs) | Report content | High (NER/LLM) | Medium |
| Topic tags | Report content | High (classification) | Medium |

## Feasibility Assessment

### What Extraction Would Require

1. **Schema Additions:**
   - `report_metadata` table or JSON column
   - `extracted_urls` table for URL tracking
   - `report_entities` table for NER results
   - `report_topics` table for topic classification

2. **Processing Pipeline:**
   - Post-synthesis extraction hook
   - Regex for URLs and citations
   - Markdown parser for structure
   - Optional: NER model for entities
   - Optional: Classification model for topics

3. **API Changes:**
   - Extended report response schemas
   - New filter/search endpoints
   - Metadata aggregation endpoints

### Implementation Effort

| Component | Effort | Dependencies |
|-----------|--------|--------------|
| URL extraction (regex) | 2-4 hours | None |
| Citation extraction | Already done | N/A |
| Markdown structure parsing | 4-8 hours | markdown-it or similar |
| Entity extraction (NER) | 8-16 hours | spaCy or API service |
| Topic classification | 8-16 hours | Custom model or LLM |
| Schema migrations | 2-4 hours | Alembic |
| API endpoints | 4-8 hours | FastAPI |

**Total estimated effort: 28-56 hours** for full implementation.

## ROI Analysis

### Current Search Capabilities

TraceLab already provides:
- **Vector search** across document chunks (semantic similarity)
- **Hybrid search** combining BM25 + vector
- **Faceted search** with project/document filters
- **Source tracing** via ReportSource relationships

### Marginal Value of Metadata Extraction

| Feature | Without Extraction | With Extraction | Delta Value |
|---------|-------------------|-----------------|-------------|
| Find reports by topic | Vector search on content | Topic filter + vector | Marginal |
| Find reports with URLs | Full-text search | URL index lookup | Marginal |
| Entity-based search | Vector search | Entity filter | Medium |
| Quality filtering | Manual review | Automated gates | Low |

### Cost-Benefit Summary

**Costs:**
- 28-56 hours implementation
- Additional schema complexity
- Processing overhead on report creation
- Maintenance of extraction logic

**Benefits:**
- Slightly faster targeted searches
- Structured metadata for future knowledge graph
- Better reporting/analytics on content

**Verdict:** The current vector search handles most discovery use cases well. Metadata extraction provides incremental improvement at significant cost.

## Recommendations

### Decision: NOT NOW

Do not implement report metadata extraction at this time.

### Rationale

1. **Vector search sufficiency**: Semantic search already finds relevant reports based on content
2. **Citation tracking exists**: `ReportSource` provides source provenance
3. **Low usage volume**: Without significant report volume, metadata indexes provide little value
4. **Future flexibility**: Can add extraction later when patterns stabilize
5. **ROI threshold**: Current needs don't justify 30-60 hour investment

### What to Do Instead

1. **Improve vector search** (higher ROI):
   - Fine-tune embedding model on research domain
   - Optimize hybrid search weights
   - Add re-ranking for report results

2. **Preserve structured data upstream**:
   - DeepSearch already returns structured protocols
   - Store `result_protocol` JSON as-is in metadata
   - Query JSON fields directly when needed

3. **Defer to knowledge graph phase**:
   - When building knowledge graph (future sprint)
   - Extract entities as graph nodes
   - Derive topics from graph clustering
   - More value from extraction at that point

### If We Decide to Extract Later

If requirements change, start with:

1. **URL extraction** - lowest effort, clear value
2. **DeepSearch metadata preservation** - already structured
3. **Entity extraction** - only after knowledge graph design

Schema addition (deferred):

```sql
-- Only add when needed
ALTER TABLE reports ADD COLUMN extracted_metadata JSONB;

-- Index for specific queries
CREATE INDEX ix_reports_urls ON reports
  USING GIN ((extracted_metadata->'urls'));
```

## Conclusion

Report metadata extraction is technically feasible but premature. The current architecture with vector search + citation tracking handles discovery and traceability needs. Revisit this decision when:

- Report volume exceeds 1000+ documents
- Knowledge graph work begins
- Specific metadata-based search patterns emerge from user feedback

---

*Analysis completed as part of Sprint 17 research track.*
