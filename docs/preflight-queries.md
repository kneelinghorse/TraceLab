# Pre-Flight Query Integration Guide

## Overview

Pre-flight queries allow autonomous research agents (like DeepSearch) to check TraceLab for existing research before launching new missions. This prevents duplicate research and enables reuse of high-quality completed work.

## Quick Start

### API Endpoint

```
POST /api/v1/pedr/preflight
```

### Request

```json
{
  "query": "passwordless authentication patterns",
  "min_quality_gates": 4,
  "status": ["complete"],
  "top_k": 5,
  "similarity_threshold": 0.70
}
```

### Response

```json
{
  "action": "reuse",
  "summary": "High-quality match found: 'Passwordless Auth Patterns' (similarity: 92%, quality gates: 5/5). Recommend reusing existing research.",
  "top_score": 0.92,
  "match_count": 1,
  "query": "passwordless authentication patterns",
  "latency_ms": 45.2,
  "matches": [
    {
      "mission_id": "DRM.0.5",
      "mission_uuid": "uuid-xxx",
      "title": "Passwordless Auth Patterns",
      "objective": "Identify proven patterns for web applications",
      "status": "complete",
      "quality_gates_passed": 5,
      "quality_gates_total": 5,
      "similarity_score": 0.92,
      "key_insights": [
        {"text": "Magic links dominate consumer applications", "index": 0},
        {"text": "WebAuthn adoption increasing for security-critical apps", "index": 1}
      ],
      "tags": ["authentication", "security"]
    }
  ],
  "filters_applied": {
    "min_quality_gates": 4,
    "status": ["complete"],
    "similarity_threshold": 0.70
  }
}
```

## Decision Criteria

The pre-flight endpoint returns one of three actions:

| Action | Condition | Meaning |
|--------|-----------|---------|
| `reuse` | similarity >= 85% AND quality_gates >= 4 AND status = complete | Use existing research, skip new research |
| `review` | similarity >= 70% AND status = complete | Review existing before proceeding |
| `proceed` | No qualifying matches | Launch new research mission |

## Integration Workflow

```
┌──────────────────────────────────┐
│      DeepSearch Agent            │
│  Receives research objective     │
└──────────────┬───────────────────┘
               │
               │ 1. Pre-flight query
               ▼
       ┌───────────────┐
       │ POST /pedr/   │
       │  preflight    │
       └───────┬───────┘
               │
       ┌───────┴───────┐
       │               │
       ▼               ▼
  ┌─────────┐    ┌──────────┐    ┌──────────┐
  │ "reuse" │    │ "review" │    │"proceed" │
  └────┬────┘    └────┬─────┘    └────┬─────┘
       │              │               │
       ▼              ▼               ▼
  Use existing   Check matches    Launch new
   research      before going     web research
                   forward
```

## Python Integration Example

```python
import requests
import os

def preflight_check(objective: str) -> dict:
    """Check TraceLab before starting new research."""

    response = requests.post(
        f"{os.environ['TRACELAB_BASE_URL']}/api/v1/pedr/preflight",
        headers={
            "Authorization": f"Bearer {os.environ['TRACELAB_TOKEN']}",
            "Content-Type": "application/json",
            "X-Agent-ID": "deepsearch-agent",
        },
        json={
            "query": objective,
            "min_quality_gates": 4,
            "status": ["complete"],
        },
    )
    response.raise_for_status()
    return response.json()


def should_research(objective: str) -> bool:
    """Determine if new research is needed."""
    result = preflight_check(objective)

    if result["action"] == "reuse":
        print(f"Using existing research: {result['matches'][0]['title']}")
        return False
    elif result["action"] == "review":
        print(f"Review existing before proceeding: {result['summary']}")
        return True  # Proceed but check existing first
    else:
        print("No existing research found. Proceeding with new mission.")
        return True
```

## CLI Example

A command-line tool is provided for testing and scripting:

```bash
# Check for existing research
python scripts/preflight_example.py "passwordless authentication patterns"

# With custom thresholds
python scripts/preflight_example.py "WebAuthn implementation" --min-gates 3

# JSON output for automation
python scripts/preflight_example.py "SSO integration" --json

# Set environment variables
export TRACELAB_BASE_URL="http://localhost:8000"
export TRACELAB_TOKEN="your-jwt-token"
```

Exit codes:
- `0`: `reuse` - Use existing research
- `2`: `review` - Review before proceeding
- `3`: `proceed` - Launch new research

## Request Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | required | Research objective or topic |
| `min_quality_gates` | int (0-5) | 4 | Minimum passing quality gates |
| `status` | string[] | ["complete"] | Allowed mission statuses |
| `top_k` | int (1-20) | 5 | Maximum matches to return |
| `similarity_threshold` | float (0-1) | 0.70 | Minimum similarity for matches |

## Response Fields

### Top-Level

| Field | Type | Description |
|-------|------|-------------|
| `action` | "reuse" \| "review" \| "proceed" | Recommended action |
| `summary` | string | Human-readable recommendation |
| `top_score` | float \| null | Highest similarity score |
| `match_count` | int | Total matches found |
| `query` | string | Original query |
| `latency_ms` | float | Query execution time |
| `matches` | array | Matching missions |
| `filters_applied` | object | Applied filter values |

### Match Object

| Field | Type | Description |
|-------|------|-------------|
| `mission_id` | string | Protocol mission ID (e.g., DRM.0.5) |
| `mission_uuid` | string | Internal UUID |
| `title` | string | Mission title |
| `objective` | string | Research objective (max 200 chars) |
| `status` | string | Mission status |
| `quality_gates_passed` | int | Passing gate count |
| `quality_gates_total` | int | Total gates (5) |
| `similarity_score` | float | Semantic similarity (0-1) |
| `key_insights` | array | Top 3 insights from synthesis |
| `created_at` | datetime | When mission was created |
| `tags` | string[] | Mission tags |

## Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | Bearer token for authentication |
| `Content-Type` | Yes | Must be `application/json` |
| `X-Agent-ID` | No | Agent identifier for telemetry |

## Telemetry

Pre-flight queries are logged to `cmos/telemetry/events/sprint-11-preflight.jsonl` for analysis:

```json
{
  "timestamp": "2025-12-05T10:00:00Z",
  "query": "passwordless authentication patterns",
  "action": "reuse",
  "top_score": 0.92,
  "match_count": 3,
  "latency_ms": 45.2,
  "min_quality_gates": 4,
  "status_filters": ["complete"],
  "agent": "deepsearch-agent"
}
```

## Quality Gates Reference

The 5 quality gates tracked:

1. **research_statement** - Clear topic, objective, and scope defined
2. **evidence_links** - Evidence items have verifiable sources
3. **synthesis_quality** - Key insights and recommendations present
4. **traceability** - Claims linked to evidence
5. **contradictions_resolved** - Conflicting information addressed

## Error Handling

| Status | Meaning | Action |
|--------|---------|--------|
| 400 | Invalid request (empty query, bad params) | Fix request |
| 401 | Authentication failed | Check token |
| 500 | Internal error | Retry or fallback |

## Performance

Target latency: < 500ms (p95)

The endpoint uses hybrid search (semantic + keyword) with quality-aware ranking. Results are cached at the search layer for repeated queries.

## See Also

- [DeepSearch Integration Contract](../cmos/planning/DeepSearch-TraceLab-Integration-Contract.md)
- [Quality-Aware Search](../docs/quality-aware-search.md)
- [Mission Protocol Schema](../docs/mission-protocol.md)
