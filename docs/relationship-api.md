# Relationship Context API

TraceLab exposes a mission-centric relationship endpoint that surfaces the
documents, insights, chunks, and sibling missions connected to a Mission
Protocol record. The endpoint performs SQL joins against the canonical mission,
document, chunk, and insight tables—no external graph database is required.

```
GET /api/v1/missions/{mission_id}/related
```

## Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `depth` | `int` | Traversal depth (`1` or `2`). Depth 1 returns core documents/insights/chunks. Depth 2 adds chunk previews and shared-artifact stats for sibling missions. |
| `entity_types` | `string[]` | Optional subset of entity types to include. Supported values: `documents`, `insights`, `chunks`, `missions`. Singular aliases (`document`, `mission`, etc.) are also accepted. |
| `min_relevance` | `float` | Filters out relationships whose maximum evidence relevance score falls below the threshold (0.0-1.0). |

## Response Shape

```jsonc
{
  "mission_id": "7c5a1c19-5f27-4ba3-9d54-90e9556dc3e8",
  "mission_identifier": "B10.4",
  "project_id": "8fcf992a-9c39-4e7e-bf41-588caabb5ea6",
  "depth": 2,
  "filters": {
    "entity_types": ["documents", "insights", "chunks", "missions"],
    "min_relevance": null
  },
  "documents": [
    {
      "id": "8d4728a8-a0d5-4ec1-a0ab-6228a75c6490",
      "name": "Q4 Field Notes",
      "file_type": "transcript",
      "source_type": "interview",
      "evidence_chunks": 2,
      "chunk_ids": [
        "ca05a63c-fff0-4ee6-9d1f-9b3fe5ff125f",
        "c0252a31-7749-4bf7-89ab-57f3ab7384a9"
      ],
      "relationship": {
        "relationship_type": "evidence_document",
        "evidence_ids": ["EV-1", "EV-2"],
        "source": "interview",
        "relevance_score": 0.86
      }
    }
  ],
  "chunks": [
    {
      "id": "ca05a63c-fff0-4ee6-9d1f-9b3fe5ff125f",
      "document_id": "8d4728a8-a0d5-4ec1-a0ab-6228a75c6490",
      "document_name": "Q4 Field Notes",
      "chunk_index": 12,
      "preview": "Participants repeatedly mentioned workflow friction ...",
      "relationship": {
        "relationship_type": "evidence_chunk",
        "evidence_ids": ["EV-1"],
        "summary": "Workflow blockers reported across finance + ops",
        "source": "Interview: ops/finance",
        "relevance_score": 0.86
      }
    }
  ],
  "insights": [
    {
      "id": "4b252b18-c388-44d6-a1d4-d5f4a37ce223",
      "title": "Finance teams bypass SOP to stay on schedule",
      "insight_type": "finding",
      "validated": true,
      "relationship": {
        "relationship_type": "derived_insight",
        "evidence_ids": ["EV-1"],
        "relevance_score": 0.86
      }
    }
  ],
  "related_missions": [
    {
      "id": "a44bc1fa-8b40-4eb3-8dc3-a95a1dff5d5a",
      "mission_identifier": "B10.2",
      "title": "Finance Workflow Analysis",
      "status": "in_progress",
      "completion_percentage": 45,
      "shared_documents": 1,
      "shared_chunks": 1,
      "shared_insights": 0,
      "relationship": {
        "relationship_type": "project_peer",
        "summary": "Shares 1 documents"
      }
    }
  ],
  "totals": {
    "documents": 1,
    "insights": 1,
    "chunks": 1,
    "missions": 1
  },
  "warnings": [],
  "cached": false
}
```

## Caching & Performance

- Results are cached for **5 minutes** via the `relationship_context` cache bucket in
  `app/services/cache_manager.py`.
- Cache keys incorporate the mission UUID, depth, entity type filters, and
  minimum relevance so different query combinations stay isolated.
- Mission updates automatically invalidate other caches (quality, validation).
  Relationship responses rely on the TTL window for freshness; run the endpoint
  after mission edits to repopulate the cache.
- All queries use SQL joins across the Mission Protocol JSON payload, document
  chunks, documents, insights, and insight_sources tables. Depth 2 adds previews
  and shared-artifact counts, so expect slightly more work relative to depth 1.

## Usage Notes

- Empty evidence lists yield zero related entities; the response includes a
  warning when evidence references missing chunk IDs.
- `min_relevance` treats missing relevance scores as `1.0` to avoid discarding
  human-entered evidence lacking AI scoring.
- `entity_types` filters remove the corresponding sections from the response but
  totals still reflect the filtered view so clients can present accurate counts.
