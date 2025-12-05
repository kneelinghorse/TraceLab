# Auto-Link Correction Loop

This document describes the automatic correction loop for evidence auto-linking failures in DeepSearch integration.

## Overview

When DeepSearch ingests missions, TraceLab automatically attempts to link evidence items to stored document chunks. When auto-linking fails, the correction loop:

1. Classifies the failure using a defined error taxonomy
2. Queues retryable failures for async retry
3. Uses exponential backoff (5s, 30s)
4. Sends webhook notifications on success/failure
5. Exports Grafana-ready telemetry for dashboards

## Error Taxonomy

| Error Type | Description | Retryable |
|------------|-------------|-----------|
| `no_embedding` | Evidence text couldn't generate embedding | Yes |
| `low_similarity` | Best match below threshold (default 0.7) | Yes |
| `no_chunks` | No chunks exist in project for matching | Yes |
| `timeout` | Qdrant/embedding service timeout | Yes |
| `validation_error` | Evidence structure invalid | No |
| `empty_content` | Evidence summary is empty/whitespace | No |
| `database_error` | Database query failed | Yes |

## Retry Strategy

Per the integration contract:

- **Max retries:** 2
- **Backoff schedule:** 5s, 30s (exponential)
- **On success:** Update chunk_id, send success webhook
- **On failure:** Mark as unlinked, send failure webhook

## API Endpoints

### GET /api/v1/deepsearch/corrections

Get correction queue status and statistics.

**Response:**
```json
{
  "stats": {
    "pending": 5,
    "in_progress": 1,
    "completed": 42,
    "failed": 3,
    "skipped": 2,
    "total": 53
  },
  "error_distribution": {
    "low_similarity": 4,
    "no_chunks": 2,
    "timeout": 2
  },
  "recent_items": [...],
  "last_updated": "2025-12-05T10:00:00Z"
}
```

### POST /api/v1/deepsearch/corrections

Trigger manual retry of pending corrections.

**Request:**
```json
{
  "mission_uuid": "uuid-optional",
  "evidence_ids": ["EV-001", "EV-002"],
  "force_retry": false,
  "callback_url": "https://deepsearch.example/webhook"
}
```

**Response:**
```json
{
  "triggered": 2,
  "skipped": 0,
  "correction_ids": ["uuid-1", "uuid-2"],
  "message": "Queued 2 items for retry, skipped 0"
}
```

### GET /api/v1/deepsearch/corrections/telemetry

Get Grafana-ready telemetry summary.

**Response:**
```json
{
  "ts": "2025-12-05T10:00:00Z",
  "event": "correction_summary",
  "pending": 5,
  "in_progress": 1,
  "completed": 42,
  "failed": 3,
  "skipped": 2,
  "total": 53,
  "success_rate": 0.933,
  "webhook_stats": {
    "total_sent": 50,
    "successful": 48,
    "failed": 2,
    "retried": 5,
    "success_rate": 0.96
  }
}
```

### POST /api/v1/deepsearch/corrections/process

Manually trigger processing of pending corrections (for testing/debugging).

### DELETE /api/v1/deepsearch/corrections/completed

Clear completed items from the queue (housekeeping).

### GET /api/v1/deepsearch/corrections/dead-letter

View failed webhook deliveries.

### DELETE /api/v1/deepsearch/corrections/dead-letter

Clear the dead letter queue.

## Webhook Notifications

### Success Notification

Sent when an evidence item is successfully linked after retry.

```json
{
  "notification_type": "correction_success",
  "mission_uuid": "uuid",
  "mission_id": "DRM.0.5",
  "evidence_id": "EV-001",
  "timestamp": "2025-12-05T10:00:00Z",
  "success": true,
  "chunk_id": "chunk-uuid",
  "similarity": 0.85,
  "retry_count": 1,
  "metadata": {}
}
```

### Failure Notification

Sent when all retry attempts are exhausted.

```json
{
  "notification_type": "correction_failure",
  "mission_uuid": "uuid",
  "mission_id": "DRM.0.5",
  "evidence_id": "EV-002",
  "timestamp": "2025-12-05T10:00:00Z",
  "success": false,
  "error_type": "low_similarity",
  "error_message": "Best match (0.55) below threshold (0.7)",
  "retry_count": 2,
  "similarity": 0.55,
  "metadata": {}
}
```

### Batch Completion

Sent when all items for a mission have been processed.

```json
{
  "notification_type": "batch_complete",
  "mission_uuid": "uuid",
  "mission_id": "DRM.0.5",
  "timestamp": "2025-12-05T10:00:00Z",
  "total_items": 10,
  "successful": 8,
  "failed": 2,
  "success_rate": 0.8,
  "items": [...]
}
```

## Telemetry Format

Telemetry is written to `cmos/telemetry/events/sprint-11-corrections.jsonl` in JSONL format for Grafana ingestion.

### Event Types

**correction_queued:**
```json
{
  "ts": "2025-12-05T10:00:00Z",
  "event": "correction_queued",
  "mission_id": "DRM.0.5",
  "evidence_id": "EV-001",
  "error_type": "low_similarity",
  "retry_count": 0,
  "similarity": 0.55,
  "threshold": 0.7,
  "status": "pending",
  "success": false
}
```

**correction_attempt:**
```json
{
  "ts": "2025-12-05T10:00:05Z",
  "event": "correction_attempt",
  "mission_id": "DRM.0.5",
  "evidence_id": "EV-001",
  "error_type": "low_similarity",
  "retry_count": 1,
  "status": "in_progress"
}
```

**correction_success:**
```json
{
  "ts": "2025-12-05T10:00:06Z",
  "event": "correction_success",
  "mission_id": "DRM.0.5",
  "evidence_id": "EV-001",
  "retry_count": 1,
  "similarity": 0.78,
  "status": "completed",
  "success": true
}
```

**webhook_success/webhook_failed:**
```json
{
  "ts": "2025-12-05T10:00:07Z",
  "event": "webhook_success",
  "mission_id": "DRM.0.5",
  "evidence_id": "EV-001",
  "notification_type": "correction_success",
  "success": true,
  "status_code": 200,
  "duration_ms": 150,
  "attempt": 1
}
```

## Grafana Dashboard Setup

### Data Source

1. Configure a Loki data source pointing to the telemetry JSONL file
2. Or use Promtail to tail the file and ship to Loki

### Suggested Panels

1. **Correction Rate** - Time series of corrections per minute
2. **Success Rate** - Gauge showing overall correction success rate
3. **Error Distribution** - Pie chart of error types
4. **Retry Histogram** - Distribution of retry counts
5. **Webhook Latency** - Histogram of webhook delivery times
6. **Queue Depth** - Time series of pending items

### Example Queries

```logql
# Correction success rate over time
sum(rate({job="tracelab"} |= "correction_success" [5m])) /
sum(rate({job="tracelab"} |= "correction_" [5m]))

# Error type distribution
sum by (error_type) (count_over_time({job="tracelab"} | json | event="correction_queued" [1h]))

# Webhook failures
{job="tracelab"} |= "webhook_failed"
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    DeepSearch Agent                      │
└───────────────────┬─────────────────────────────────────┘
                    │ POST /api/v1/deepsearch/ingest
                    ▼
┌─────────────────────────────────────────────────────────┐
│              TraceLab Ingestion Endpoint                 │
│  - Validates mission                                     │
│  - Runs evidence auto-linking                           │
│  - Queues failed items to CorrectionQueueService        │
└───────────────────┬─────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
┌───────────────────┐   ┌───────────────────────────────┐
│ Success Response  │   │   CorrectionQueueService       │
│ (chunk_ids set)   │   │   - Exponential backoff        │
└───────────────────┘   │   - Max 2 retries              │
                        │   - Telemetry logging          │
                        └───────────┬───────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌───────────┐   ┌───────────┐   ┌───────────┐
            │ Retry #1  │   │ Retry #2  │   │ Final     │
            │ (5s wait) │   │ (30s wait)│   │ Status    │
            └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
                  │               │               │
                  └───────────────┴───────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────────┐
                    │      WebhookClient          │
                    │  - Send success/failure     │
                    │  - Retry with backoff       │
                    │  - Dead letter queue        │
                    └─────────────┬───────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────────┐
                    │   DeepSearch Webhook        │
                    │   Receives notifications    │
                    └─────────────────────────────┘
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `MAX_RETRIES` | 2 | Maximum retry attempts per integration contract |
| `BACKOFF_SCHEDULE` | [5, 30] | Seconds between retries |
| `similarity_threshold` | 0.7 | Minimum similarity for linking |
| `webhook_timeout` | 10s | Webhook delivery timeout |
| `webhook_max_retries` | 3 | Max attempts for webhook delivery |

## Monitoring

### Key Metrics

- **Correction Success Rate**: Target >95%
- **Webhook Delivery Rate**: Target >99%
- **Queue Depth**: Should trend toward 0
- **Retry Distribution**: Most items should succeed on first retry

### Alerts

1. **High Queue Depth**: >100 pending items for >5 minutes
2. **Low Success Rate**: <90% over 1 hour
3. **Webhook Failures**: >5% failure rate
4. **Dead Letter Growth**: >10 items added in 1 hour
