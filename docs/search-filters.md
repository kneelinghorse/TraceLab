# Search Filter & Facets API

TraceLab's Sprint 09 faceted search backend introduces first-class filtering support across the `/api/v1/search` RAG endpoint, the `/api/v1/retrieval/search` semantic endpoint, and the new `/api/v1/facets` helper. This document outlines the supported filters, payload schemas, and validation behaviors.

## Supported Filters

All search and retrieval requests now accept these optional parameters:

| Field | Type | Notes |
| --- | --- | --- |
| `project_id` | UUID | Restricts results to a single project (existing behavior). |
| `document_id` | UUID | Restricts results to a single document. |
| `document_types` | `List[str]` | Matches document `file_type` values (e.g., `transcript`, `survey`). |
| `source_types` | `List[str]` | Matches `source_type` metadata (e.g., `interview`, `analysis`). Backwards-compatible with the legacy `source_type` string. |
| `date_from` / `date_to` | ISO `YYYY-MM-DD` | Filters by `collection_date` range; both endpoints inclusive. |
| `tags` | `List[str]` | Matches tag names assigned to the source document (OR semantics). |

Filter semantics follow a strict AND across different categories and an OR within each list. For example, supplying `document_types=["transcript","report"]` and `tags=["governance"]` returns transcripts or reports that have the `governance` tag.

## `/api/v1/search` (RAG) Payload Example

```json
{
  "query": "How did the sustainability program evolve?",
  "top_k": 8,
  "search_mode": "hybrid",
  "project_id": "6d8ff1a2-4e7d-4f3c-832c-013386bd0512",
  "document_types": ["transcript", "report"],
  "source_types": ["interview"],
  "date_from": "2025-01-01",
  "date_to": "2025-10-31",
  "tags": ["executive", "governance"],
  "temperature": 0.2,
  "max_tokens": 400
}
```

The response's `sources` array propagates `document_type`, `source_type`, `collection_date`, and `tags` for each chunk so UI layers can render filter context without additional queries.

## `/api/v1/facets` Endpoint

Use the facets endpoint to populate dropdown values and counts. It shares the same filter schema (except for `document_id`, `query`, or scoring params).

**Request**

```http
POST /api/v1/facets
Authorization: Bearer <token>
Content-Type: application/json

{
  "project_id": "6d8ff1a2-4e7d-4f3c-832c-013386bd0512",
  "document_types": ["transcript"],
  "tags": ["executive"]
}
```

**Response**

```json
{
  "projects": [
    {"value": "6d8ff1a2-4e7d-4f3c-832c-013386bd0512", "label": "TraceLab Test Project", "count": 12}
  ],
  "document_types": [
    {"value": "transcript", "label": "transcript", "count": 8},
    {"value": "report", "label": "report", "count": 4}
  ],
  "source_types": [
    {"value": "interview", "label": "interview", "count": 8}
  ],
  "tags": [
    {"value": "executive", "label": "executive", "count": 6}
  ],
  "date_range": {
    "min": "2025-01-05",
    "max": "2025-11-13"
  }
}
```

Counts respect any filters supplied in the request, enabling cascading UI experiences (e.g., selecting a tag updates available document types automatically).

## Implementation Notes

- Filters propagate to both Qdrant (semantic) and PostgreSQL keyword paths. When metadata is unavailable (e.g., legacy embeddings without tags), results are omitted rather than returning potentially incorrect hits.
- A new TTL/semantic cache signature incorporates the filter combination to avoid cross-contamination between filtered/unfiltered requests.
- PostgreSQL performance is guarded by fresh indexes on `documents.file_type`, `documents.source_type`, `documents.collection_date`, and `document_tags.tag_id`. Apply Alembic revision `007_add_faceted_filter_indexes`.
- Keyword search filtering uses SQL-level constraints for document/source types and dates alongside a correlated subquery for tag matching. A final metadata check ensures OR semantics for tag lists even when multiple tags resolve to the same document.
- Semantic search filtering augments chunk metadata using a lightweight lookup against the relational store to avoid rewriting existing Qdrant payloads.

Refer to `app/api/v1/search.py`, `app/api/v1/facets.py`, and `app/services/faceted_search.py` for canonical usage examples. Tests under `tests/test_faceted_search.py` demonstrate expected outcomes for filtering and facet aggregation.
