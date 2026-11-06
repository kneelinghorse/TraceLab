# Sprint 03 Mission Protocol Evaluation

**Generated:** 2025-11-08T19:19:37.545575+00:00

## Executive Summary

- **Metrics Met:** 6/6
- **Metrics Unmet:** 0/6
- References: docs/quality_gates.md, docs/mission_protocol_validation.md

## Metric Details

### ✅ Mission Protocol validation coverage >95% across API/service/database layers

- **Actual:** 0.975
- **Target:** 0.95

**Details:**
```json
{
  "total_validations": 40,
  "successful_validations": 39,
  "coverage": 0.975,
  "failed_missions": [
    {
      "mission_id": "MP-VAL-017",
      "missing_layers": [
        "database"
      ],
      "detail": "Constraint enforcement rejected payload due to missing timestamps."
    }
  ],
  "reference": "docs/quality_gates.md"
}
```

### ✅ Quality gates block invalid missions with actionable remediation guidance

- **Actual:** 1.0
- **Target:** 1.0

**Details:**
```json
{
  "gate_activity": {
    "research_statement": {
      "total": 6,
      "fails": 0
    },
    "evidence_links": {
      "total": 6,
      "fails": 1
    },
    "contradictions_resolved": {
      "total": 6,
      "fails": 0
    },
    "synthesis_quality": {
      "total": 6,
      "fails": 1
    },
    "traceability": {
      "total": 6,
      "fails": 1
    }
  },
  "failure_count": 3,
  "actionable_failures": 3,
  "actionable_ratio": 1.0
}
```

### ✅ API stability (>99% uptime, <500ms p95 latency)

- **Actual:** {"min_uptime": 0.9991, "p95_latency_ms": 320}
- **Target:** {"uptime": 0.99, "p95_latency_ms": 500}

**Details:**
```json
{
  "avg_uptime": 0.9995200000000001,
  "min_uptime": 0.9991,
  "aggregated_p95_latency_ms": 320,
  "avg_error_rate": 0.0013,
  "samples": 5
}
```

### ✅ YAML round-trip accuracy (import/export/import parity)

- **Actual:** 15
- **Target:** 15

**Details:**
```json
{
  "total_round_trips": 15,
  "perfect_round_trips": 15,
  "round_trip_failures": 0,
  "total_fields_reviewed": 630
}
```

### ✅ Evidence linking integrity (chunk presence + relevance >= 0.8)

- **Actual:** {"missing_chunk_events": 0, "average_relevance": 0.8649999999999999}
- **Target:** {"missing_chunk_events": 0, "average_relevance": 0.8}

**Details:**
```json
{
  "checked_missions": 12,
  "missing_chunk_events": 0,
  "average_relevance": 0.8649999999999999
}
```

### ✅ Progress tracking accuracy within ±5% of field population

- **Actual:** {"within_tolerance": 10, "samples": 10}
- **Target:** {"tolerance": 0.05}

**Details:**
```json
{
  "samples": 10,
  "within_tolerance": 10,
  "out_of_tolerance": 0,
  "tolerance": 0.05
}
```

