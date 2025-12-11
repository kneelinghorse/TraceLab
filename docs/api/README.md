# TraceLab API Reference

TraceLab exposes a RESTful API for document management, search, and research mission handling. All endpoints use the `/api/v1` prefix.

## Authentication

Most endpoints require Bearer token authentication:

```http
Authorization: Bearer <jwt_token>
```

### Auth Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/login` | Obtain JWT token |
| `POST` | `/api/v1/auth/refresh` | Refresh expired token |
| `POST` | `/api/v1/auth/api-keys` | Create API key |
| `GET` | `/api/v1/auth/api-keys` | List API keys |
| `DELETE` | `/api/v1/auth/api-keys/{key_id}` | Revoke API key |

---

## Search

### PEDR Unified Search

Primary search interface combining 5 layers with RRF fusion.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/pedr/search` | Execute PEDR multi-layer search |

**Request**:
```json
{
  "query": "user authentication patterns",
  "top_k": 10,
  "rerank_mode": "full",
  "project_id": "uuid",
  "source_type": "interview",
  "enable_lexical": true,
  "enable_semantic": true
}
```

See [PEDR Search Architecture](../architecture/PEDR-search.md) for layer details.

### RAG Search (Legacy)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/search` | Execute RAG query with LLM answer generation |

### Semantic Retrieval

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/retrieval/search` | Vector-only semantic search |

### Faceted Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/facets` | Get facet counts for filtering |

### Search History & Saved Searches

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/search/history` | List recent searches |
| `DELETE` | `/api/v1/search/history` | Clear search history |
| `POST` | `/api/v1/search/replay/{history_id}` | Replay saved search |
| `GET` | `/api/v1/saved-searches` | List saved searches |
| `POST` | `/api/v1/saved-searches` | Save a search |
| `PUT` | `/api/v1/saved-searches/{id}` | Update saved search |
| `DELETE` | `/api/v1/saved-searches/{id}` | Delete saved search |
| `POST` | `/api/v1/saved-searches/{id}/execute` | Execute saved search |

---

## Documents

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/documents` | List documents (paginated) |
| `POST` | `/api/v1/documents/upload` | Upload document |
| `GET` | `/api/v1/documents/{id}` | Get document details |
| `GET` | `/api/v1/documents/{id}/download` | Download original file |
| `GET` | `/api/v1/documents/{id}/chunks` | List document chunks |
| `POST` | `/api/v1/documents/{id}/process` | Trigger reprocessing |
| `DELETE` | `/api/v1/documents/{id}` | Soft delete document |
| `POST` | `/api/v1/documents/{id}/restore` | Restore deleted document |
| `GET` | `/api/v1/documents/coverage/report` | Coverage statistics |
| `GET` | `/api/v1/documents/service/health` | Service health check |

### Document Fields

| Field | Description |
|-------|-------------|
| `source_type` | interview, survey, log, artifact, etc. |
| `source_origin` | `upload`, `synthesized`, `imported` |
| `file_type` | MIME type |
| `collection_date` | When data was collected |

---

## Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/projects` | List projects |
| `POST` | `/api/v1/projects` | Create project |
| `GET` | `/api/v1/projects/{id}` | Get project details |
| `PUT` | `/api/v1/projects/{id}` | Update project |
| `DELETE` | `/api/v1/projects/{id}` | Soft delete project |
| `POST` | `/api/v1/projects/{id}/restore` | Restore project |
| `GET` | `/api/v1/projects/{id}/stats` | Project statistics |

---

## Collections

Research collections group related chunks for synthesis.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/collections` | List collections |
| `POST` | `/api/v1/collections` | Create collection |
| `GET` | `/api/v1/collections/{id}` | Get collection details |
| `GET` | `/api/v1/collections/{id}/export` | Export as markdown |
| `PUT` | `/api/v1/collections/{id}` | Update collection |
| `DELETE` | `/api/v1/collections/{id}` | Delete collection |
| `POST` | `/api/v1/collections/{id}/chunks` | Add chunk to collection |
| `DELETE` | `/api/v1/collections/{id}/chunks/{chunk_id}` | Remove chunk |

---

## Missions

Mission Protocol implementation for research tracking.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/missions` | List missions (paginated) |
| `POST` | `/api/v1/missions` | Create mission |
| `GET` | `/api/v1/missions/{id}` | Get mission details |
| `PUT` | `/api/v1/missions/{id}` | Update mission |
| `DELETE` | `/api/v1/missions/{id}` | Delete mission |
| `POST` | `/api/v1/missions/{id}/submit` | Submit to DeepSearch |
| `POST` | `/api/v1/missions/{id}/promote-report` | Promote to document |
| `GET` | `/api/v1/missions/{id}/related` | Get related entities |

See [Mission Protocol Architecture](../architecture/mission-protocol.md) for schema details.

### Quality Gates

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/missions/{id}/quality` | Get quality gate report |
| `POST` | `/api/v1/quality/automated/run` | Run automated quality checks |
| `GET` | `/api/v1/quality/automated/history/{id}` | Quality check history |

---

## Reports

Synthesis outputs and report management.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/reports` | List reports |
| `POST` | `/api/v1/reports` | Create report |
| `GET` | `/api/v1/reports/{id}` | Get report details |
| `PUT` | `/api/v1/reports/{id}` | Update report |
| `DELETE` | `/api/v1/reports/{id}` | Delete report |

### Synthesis

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/synthesize` | Generate synthesis from chunks |
| `GET` | `/api/v1/synthesis/cache/stats` | Synthesis cache statistics |

---

## DeepSearch Integration

External agent integration endpoints.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/deepsearch/ingest` | Ingest completed mission |

### Preflight Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/pedr/preflight` | Quick search for mission planning |

### Correction Loop

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/deepsearch/corrections` | List pending corrections |
| `POST` | `/api/v1/deepsearch/corrections` | Create correction |
| `GET` | `/api/v1/deepsearch/corrections/{id}` | Get correction details |
| `POST` | `/api/v1/deepsearch/corrections/{id}/apply` | Apply correction |
| `DELETE` | `/api/v1/deepsearch/corrections/{id}` | Delete correction |
| `GET` | `/api/v1/deepsearch/corrections/pending` | Pending corrections |
| `DELETE` | `/api/v1/deepsearch/corrections/pending` | Clear pending |

See [DeepSearch Integration](../integration/deepsearch.md) for agent workflows.

---

## Graph Expansion

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/pedr/related/{urn}` | Get related entities by URN |

---

## Administration

### Cache Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/cache/stats` | Cache statistics |
| `POST` | `/api/v1/cache/clear` | Clear caches |

### Qdrant Admin

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/qdrant-admin/stats` | Qdrant collection stats |
| `GET` | `/api/v1/qdrant-admin/health` | Qdrant health check |
| `POST` | `/api/v1/qdrant-admin/config/hnsw` | Update HNSW config |

### System Admin

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/admin/init-qdrant` | Initialize Qdrant collection |
| `GET` | `/api/v1/admin/health` | Admin health check |
| `GET` | `/api/v1/admin/dashboard` | Admin dashboard (HTML) |
| `GET` | `/api/v1/admin/dashboard/data` | Dashboard data (JSON) |
| `GET` | `/api/v1/admin/dashboard/export` | Export dashboard data |

### PII Redaction

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/redaction/redact` | Redact PII from text |
| `GET` | `/api/v1/redaction/health` | Redaction service health |

### Monitoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/monitoring/costs` | OpenAI cost metrics |
| `GET` | `/api/v1/monitoring/performance` | Performance telemetry |

---

## Health Checks

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Basic health |
| `GET` | `/api/v1/health/db` | Database health |
| `GET` | `/api/v1/health/qdrant` | Qdrant health |
| `GET` | `/api/v1/health/ready` | Readiness probe |

---

## Webhooks

Webhook endpoint uses signature-based authentication (no JWT required):

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/webhooks/deepsearch` | DeepSearch callback handler |

---

## Response Formats

### Paginated Response

```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "size": 20,
  "pages": 5
}
```

### Error Response

```json
{
  "detail": "Error message"
}
```

Or structured:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Field validation failed",
    "details": {...}
  }
}
```

---

## Rate Limits

Currently no enforced rate limits. Monitor via `/api/v1/monitoring/performance`.

---

## Related Documentation

- [PEDR Search Architecture](../architecture/PEDR-search.md) - Search layer details
- [Mission Protocol](../architecture/mission-protocol.md) - Mission schema
- [DeepSearch Integration](../integration/deepsearch.md) - Agent integration
- [Authentication Guide](../authentication.md) - Auth setup
