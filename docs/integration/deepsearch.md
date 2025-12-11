# DeepSearch Integration Guide

This guide explains how DeepSearch agents integrate with TraceLab for research mission management, evidence retrieval, and quality-validated ingestion.

## Overview

DeepSearch agents interact with TraceLab through:

1. **Preflight queries** - Check for existing research before starting
2. **Search integration** - Retrieve evidence during research
3. **Mission ingestion** - Submit completed missions with quality validation
4. **Correction loop** - Handle failed evidence auto-linking

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ DeepSearch  │────▶│  TraceLab   │◀────│  Evidence   │
│   Agent     │     │    API      │     │   Corpus    │
└─────────────┘     └─────────────┘     └─────────────┘
      │                    │
      │ 1. Preflight       │ 2. Search
      │ 3. Ingest          │ 4. Corrections
      ▼                    ▼
┌─────────────────────────────────────────────────────┐
│            Mission Protocol Engine                  │
│  ┌─────────┐ ┌──────────┐ ┌─────────────────────┐  │
│  │Evidence │ │Synthesis │ │   Quality Gates     │  │
│  │Linking  │ │ Storage  │ │research_statement   │  │
│  │         │ │          │ │evidence_links       │  │
│  │         │ │          │ │synthesis_quality    │  │
│  └─────────┘ └──────────┘ │traceability         │  │
│                           │contradictions       │  │
│                           └─────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 1. Preflight Queries

Before starting new research, agents should check for existing relevant missions.

### Endpoint

```http
POST /api/v1/pedr/preflight
Authorization: Bearer <token>
X-Agent-Id: deepsearch-agent-001  # Optional
Content-Type: application/json

{
  "query": "passwordless authentication patterns",
  "top_k": 5,
  "similarity_threshold": 0.70,
  "quality_threshold": 3
}
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | required | Research topic or question |
| `top_k` | int | 5 | Maximum matches to return |
| `similarity_threshold` | float | 0.70 | Minimum similarity for matches |
| `quality_threshold` | int | 3 | Minimum quality gates passed |
| `project_id` | UUID | null | Filter to specific project |

### Response Actions

| Action | Condition | Agent Behavior |
|--------|-----------|----------------|
| `reuse` | similarity >= 85%, quality >= 4, status = complete | Use existing mission directly |
| `review` | similarity >= 70%, status = complete | Manual review recommended |
| `proceed` | No qualifying matches | Start new research |

### Example Response

```json
{
  "action": "reuse",
  "summary": "High-quality match found: 'Passwordless Auth Patterns' (similarity: 92%, quality gates: 5/5)",
  "top_score": 0.92,
  "match_count": 3,
  "query": "passwordless authentication patterns",
  "latency_ms": 45.2,
  "matches": [
    {
      "mission_id": "DRM.0.5",
      "title": "Passwordless Auth Patterns",
      "objective": "Identify proven patterns for web applications",
      "status": "complete",
      "quality_gates_passed": 5,
      "similarity_score": 0.92
    }
  ]
}
```

---

## 2. Search Integration

During research, agents use PEDR search to find relevant evidence.

### Primary Search Endpoint

```http
POST /api/v1/pedr/search
Authorization: Bearer <token>
Content-Type: application/json

{
  "query": "user frustration with password requirements",
  "top_k": 20,
  "rerank_mode": "full",
  "project_id": "1ee7-...-0bc3",
  "source_type": "interview"
}
```

### Key Parameters for Agents

| Parameter | Usage |
|-----------|-------|
| `project_id` | Scope search to mission's project |
| `source_type` | Filter by data type (interview, survey, etc.) |
| `source_origin` | Filter by origin: `upload`, `synthesized`, `imported` |
| `min_quality_gates` | Require validated content |

### Dependency Search

To find evidence from synthesized/derived sources:

```json
{
  "query": "authentication research findings",
  "source_origin": "synthesized"
}
```

See [PEDR Search Architecture](../architecture/PEDR-search.md) for full layer documentation.

---

## 3. Mission Ingestion

Submit completed missions with automatic evidence linking and quality validation.

### Endpoint

```http
POST /api/v1/deepsearch/ingest
Authorization: Bearer <token>
Content-Type: application/json
```

### Request Body

```json
{
  "project_id": "1ee7-...-0bc3",
  "auto_create_project": false,
  "project_name": null,
  "similarity_threshold": 0.75,
  "callback_url": "https://deepsearch.example.com/webhooks/tracelab",
  "mission": {
    "mission_id": "DSR.10.1",
    "title": "Login Friction Analysis",
    "status": "complete",
    "research_statement": {
      "topic": "User login experience",
      "objective": "Identify friction points in authentication flows",
      "scope": "Mobile app users, Q4 2024"
    },
    "key_questions": [
      {
        "question": "What causes users to abandon login?",
        "status": "answered",
        "answer": "Password complexity (42%), 2FA friction (31%), timeouts (27%)",
        "confidence": 0.85
      }
    ],
    "synthesis": {
      "key_insights": [
        "Password complexity rules cause 42% of login abandonment"
      ],
      "recommendations": [
        "Extend session timeout to 15 minutes"
      ]
    },
    "evidence": [
      {
        "evidence_id": "EV-001",
        "source": "User Interview #12",
        "summary": "User reported abandoning login after 3 failed 2FA attempts"
      }
    ],
    "quality_checkpoints": [
      {"gate": "research_statement", "status": "pass"},
      {"gate": "evidence_links", "status": "pass"},
      {"gate": "synthesis_quality", "status": "pass"},
      {"gate": "traceability", "status": "pass"},
      {"gate": "contradictions_resolved", "status": "pass"}
    ]
  }
}
```

### Project Resolution

| Scenario | Parameters |
|----------|------------|
| Existing project | `project_id: "uuid"` |
| Auto-create project | `auto_create_project: true, project_name: "Name"` |

### Success Response

```json
{
  "mission_uuid": "08be-...-2fd5",
  "mission_id": "DSR.10.1",
  "project_id": "1ee7-...-0bc3",
  "status": "complete",
  "quality_gates_passed": true,
  "quality_gates": {
    "research_statement": {"status": "pass", "details": "..."},
    "evidence_links": {"status": "pass", "details": "3/3 linked"},
    "synthesis_quality": {"status": "pass", "details": "..."},
    "traceability": {"status": "pass", "details": "..."},
    "contradictions_resolved": {"status": "pass", "details": "..."}
  },
  "auto_linking": {
    "attempted": 3,
    "linked": 3,
    "skipped": 0,
    "failed": 0,
    "success_rate": 1.0,
    "threshold": 0.75,
    "matches": [
      {"evidence_id": "EV-001", "chunk_id": "f6c9-...-f1d8", "similarity": 0.91}
    ]
  }
}
```

### Quality Gate Failure

```json
{
  "success": false,
  "error": {
    "code": "QUALITY_GATE_FAILURE",
    "message": "Mission validation failed - quality gates not passed",
    "details": {
      "failing_gates": ["evidence_links", "traceability"],
      "quality_gates": {...},
      "mission_id": "DSR.10.1",
      "auto_linking": {
        "attempted": 3,
        "linked": 1,
        "failed": 2,
        "success_rate": 0.33
      }
    }
  }
}
```

---

## 4. Evidence Auto-Linking

TraceLab automatically links evidence summaries to document chunks.

### How It Works

1. Agent submits mission with evidence summaries (URL-only is fine)
2. TraceLab searches project chunks for similar content
3. Matches above threshold get `chunk_id` assigned
4. Quality gates evaluate chunk-backed evidence

### Similarity Threshold

```json
{
  "similarity_threshold": 0.75
}
```

- **Default**: 0.70
- **Range**: 0.0 - 1.0 (clamped)
- **Higher**: More precise matches, more failures
- **Lower**: More matches, potential false positives

### Link Failure Handling

When evidence fails to auto-link:

1. Mission still creates (if quality gates pass)
2. Failed items queued for correction
3. Callback notifies agent if URL provided

---

## 5. Correction Loop

Handle failed evidence links asynchronously.

### List Pending Corrections

```http
GET /api/v1/deepsearch/corrections/pending
Authorization: Bearer <token>
```

### Get Correction Details

```http
GET /api/v1/deepsearch/corrections/{correction_id}
Authorization: Bearer <token>
```

### Apply Correction

Manually link evidence to a chunk:

```http
POST /api/v1/deepsearch/corrections/{correction_id}/apply
Authorization: Bearer <token>
Content-Type: application/json

{
  "chunk_id": "f6c9-...-f1d8",
  "manual_review_notes": "Linked to interview transcript chunk #47"
}
```

### Delete Correction

```http
DELETE /api/v1/deepsearch/corrections/{correction_id}
Authorization: Bearer <token>
```

### Response with Corrections

When ingestion queues corrections:

```json
{
  "mission_uuid": "08be-...-2fd5",
  "...",
  "corrections": {
    "queued_count": 2,
    "correction_ids": ["corr-001", "corr-002"],
    "callback_url": "https://deepsearch.example.com/webhooks/tracelab"
  }
}
```

---

## 6. Mission Submission to DeepSearch

Trigger DeepSearch to execute a mission from TraceLab:

```http
POST /api/v1/missions/{mission_id}/submit
Authorization: Bearer <token>
Content-Type: application/json

{
  "priority": "normal",
  "callback_url": "https://your-app.com/webhooks/deepsearch"
}
```

---

## 7. Report Promotion

Promote completed mission reports to first-class documents:

```http
POST /api/v1/missions/{mission_id}/promote-report
Authorization: Bearer <token>
Content-Type: application/json

{
  "document_name": "Login Friction Analysis - Final Report",
  "source_type": "research_synthesis"
}
```

This creates a new document with:
- `source_origin: "synthesized"`
- `source_mission_id` pointing to original mission
- Full text content for vector indexing

---

## Best Practices

### 1. Always Preflight

```python
# Before starting research
preflight = client.post("/api/v1/pedr/preflight", json={
    "query": mission_objective,
    "similarity_threshold": 0.75
})

if preflight["action"] == "reuse":
    return preflight["matches"][0]  # Use existing
elif preflight["action"] == "review":
    # Present to human for decision
    pass
else:
    # Proceed with new research
    pass
```

### 2. Structure Evidence for Linking

Include descriptive summaries that match document content:

```json
{
  "evidence_id": "EV-001",
  "source": "Interview Transcript - User #12",
  "summary": "Direct quote: 'I gave up after the third 2FA code failed'"
}
```

### 3. Handle Quality Gate Failures

```python
response = client.post("/api/v1/deepsearch/ingest", json=payload)

if response.status_code == 400:
    error = response.json()["error"]
    if error["code"] == "QUALITY_GATE_FAILURE":
        failing = error["details"]["failing_gates"]
        # Address specific failures
        if "evidence_links" in failing:
            # Improve evidence summaries
            pass
```

### 4. Use Callbacks for Async Operations

```json
{
  "callback_url": "https://deepsearch.example.com/webhooks/tracelab"
}
```

TraceLab posts to this URL when:
- Corrections are applied
- Quality gates re-evaluated
- Mission status changes

---

## Related Documentation

- [PEDR Search Architecture](../architecture/PEDR-search.md) - Search layer details
- [Mission Protocol](../architecture/mission-protocol.md) - Schema reference
- [API Overview](../api/README.md) - Full endpoint reference
- [Quality Gates](../quality_gates.md) - Gate definitions
