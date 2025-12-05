# PEDR Delta Sync Architecture

**Status**: Implemented (Sprint 11)
**Reference**: cmos/planning/PEDR-docs/tracelab-to-pedr-mapping.md

## Overview

The PEDR (Protocol-Enhanced Deep Research) Delta Sync Service provides event-driven synchronization of Tracelab research artifacts to the PEDR search index. It supports:

- **Delta Detection**: Sync only entities changed since the last sync
- **Event-Driven Triggers**: Sub-30-second latency from mission completion to PEDR availability
- **Governance Metadata**: PII flags and business impact scores propagated
- **Manifest Transformation**: Mission Protocol structure to PEDR catalog format

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Tracelab Application                                             │
│                                                                  │
│  ┌──────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │ Mission      │ -> │ Sync Event       │ -> │ Delta Sync    │  │
│  │ Completion   │    │ Emitter          │    │ Service       │  │
│  └──────────────┘    └──────────────────┘    └───────┬───────┘  │
│                                                       │          │
│  ┌──────────────┐    ┌──────────────────┐           │          │
│  │ Document     │ -> │ Queue (Optional) │ <---------┘          │
│  │ Processing   │    └──────────────────┘                       │
│  └──────────────┘                                               │
│                                                                  │
└───────────────────────────────────┬─────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Manifest Transformer                                             │
│                                                                  │
│  Mission Protocol YAML  →  PEDR Manifest                        │
│  - URN generation (urn:research:mission:{id})                   │
│  - Governance scoring (PII, impact 1-10)                        │
│  - Relationship bindings (project, chunks, documents)           │
│                                                                  │
└───────────────────────────────────┬─────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ PEDR Ingestion Endpoint                                          │
│                                                                  │
│  POST /api/v1/catalog/ingest                                    │
│  - Batch manifests (configurable batch size)                    │
│  - Retry with exponential backoff                               │
│  - Sync state persistence                                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. SyncState Model (`app/models/sync_state.py`)

Tracks synchronization state per entity type:

```python
class SyncState:
    entity_type: str       # mission | document | insight
    last_sync_at: datetime # Last successful sync timestamp
    sync_count: int        # Total entities synced
    last_entity_id: str    # Cursor for pagination
    metadata: dict         # Additional sync metadata
```

### 2. Manifest Transformer (`app/services/pedr/manifest_transformer.py`)

Converts Tracelab entities to PEDR manifest format:

```python
# Mission to PEDR Manifest
result = transformer.transform_mission(
    mission_id="uuid-123",
    mission_data=mission.mission_data,
    quality_gates=mission.quality_gates,
    project_id=str(mission.project_id),
    status=mission.status,
)

# Output
PEDRManifest(
    urn="urn:research:mission:M001",
    purpose="Research objective from mission",
    description="Mission title",
    element_type="mission",
    element_intent="Read",
    governance_pii=False,
    governance_impact=7,
    bindings={"project_id": "...", "evidence_chunks": [...]}
)
```

### 3. Delta Sync Service (`app/services/pedr/delta_sync.py`)

Orchestrates sync operations:

```python
service = get_delta_sync_service()

# Delta sync (only changed entities)
result = service.sync_missions(SyncMode.DELTA)

# Full sync (all entities)
result = service.sync_missions(SyncMode.FULL)

# Get sync status
status = service.get_sync_status()
# {"mission": {"last_sync_at": "...", "sync_count": 42}}

# Check parity
parity = service.check_parity(EntityType.MISSION)
# ParityCheckResult(local_count=100, remote_count=100, in_sync=True)
```

### 4. Sync Event Emitter (`app/services/pedr/sync_events.py`)

Event-driven sync triggers:

```python
emitter = get_sync_event_emitter()

# Register handler for mission completions
def handle_mission_sync(event: SyncEvent):
    service.sync_missions(SyncMode.DELTA)

emitter.on(SyncEventType.MISSION_COMPLETED, handle_mission_sync)

# Emit when mission completes
emit_mission_completed(emitter, mission_id, project_id=project_id)
```

## CLI Commands

```bash
# Delta sync (default - only changed entities)
python -m app.cli.pedr sync --delta

# Full sync (all entities)
python -m app.cli.pedr sync --full

# Dry run (transform but don't ingest)
python -m app.cli.pedr sync --dry-run

# Sync specific entity type
python -m app.cli.pedr sync --entity-type mission

# Show sync status
python -m app.cli.pedr status

# Check parity
python -m app.cli.pedr parity

# Show pending entities
python -m app.cli.pedr pending
```

## Governance Scoring

### Impact Score Calculation (1-10 range)

| Factor | Score Adjustment |
|--------|------------------|
| Base score | 5 |
| Status = complete | +2 |
| All quality gates pass | +1 |
| Validated mission | +1 |
| **Maximum** | **10** |

### PII Detection

PII is flagged from:
- Explicit governance flags: `mission_data.governance.pii`
- Tags: `pii`, `privacy`, `redaction`, `sensitive`
- Content patterns: Email, phone, SSN regex matching

## Manifest Transformation

### Mission → PEDR Catalog

| Tracelab Field | PEDR Field | Notes |
|----------------|------------|-------|
| `mission_data.missionId` | `urn` | Prefixed with `urn:research:mission:` |
| `research_statement.objective` | `purpose` | Truncated to 500 chars |
| `mission_data.name` | `description` | Mission title |
| - | `context_domain` | Always "research" |
| - | `element_type` | Always "mission" |
| - | `element_intent` | Always "Read" |
| Quality gates + status | `governance_impact` | Calculated 1-10 |
| `governance.pii` | `governance_pii` | Boolean |
| `evidence[].chunk_id` | `bindings.evidence_chunks` | Array of chunk IDs |
| `project_id` | `bindings.project_id` | UUID |

### Document → PEDR Catalog

| Tracelab Field | PEDR Field |
|----------------|------------|
| `id` | `urn` (urn:research:document:{id}) |
| `name` | `description` |
| `file_type` | `element_type` |
| `content` (first 500 chars) | `purpose` |

## Telemetry

Sync events are logged to `cmos/telemetry/events/sprint-11-pedr-sync.jsonl`:

```json
{
  "ts": "2025-12-05T12:00:00Z",
  "event": "pedr_sync",
  "entity_type": "mission",
  "mode": "delta",
  "synced_count": 5,
  "failed_count": 0,
  "duration_ms": 1250.5,
  "success": true
}
```

## Error Handling

### Retry Strategy

- Max retries: 3
- Delay: Exponential backoff (1s, 2s, 4s)
- On persistent failure: Log error, continue with next batch

### Dead Letter Queue

Failed entities are logged for manual review:
- Entity ID and type
- Error message
- Timestamp
- Retry count

## Integration Points

### Hooking into Mission Completion

```python
from app.services.pedr import emit_mission_completed, get_sync_event_emitter

# In your mission completion handler
def on_mission_complete(mission):
    emit_mission_completed(
        get_sync_event_emitter(),
        str(mission.id),
        project_id=str(mission.project_id),
        status=mission.status,
    )
```

### Scheduled Catch-up Sync

For resilience, run periodic delta syncs:

```python
# In a scheduler (e.g., APScheduler, Celery beat)
@scheduler.scheduled_job('interval', hours=1)
def hourly_sync():
    service = get_delta_sync_service()
    service.sync_all(SyncMode.DELTA)
```

## Rebuild Process

To fully rebuild PEDR from Tracelab:

1. Clear PEDR catalog: `DELETE FROM protocol_catalog WHERE urn LIKE 'urn:research:%'`
2. Reset sync state: `DELETE FROM sync_states`
3. Run full sync: `python -m app.cli.pedr sync --full`
4. Verify parity: `python -m app.cli.pedr parity`

## Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Sync latency (delta) | <30 seconds | Event to PEDR availability |
| Batch size | 100 entities | Configurable |
| Throughput | 1000 entities/minute | Sustained sync rate |

## Future Enhancements

1. **Bidirectional Sync**: Handle updates from PEDR back to Tracelab
2. **Webhook Integration**: Direct PEDR callbacks on entity changes
3. **Chunk-Level Indexing**: Granular search at chunk level
4. **Vector Embedding Sync**: Push embeddings for semantic search
