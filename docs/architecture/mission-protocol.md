# Mission Protocol Architecture

The **Mission Protocol** defines the schema and lifecycle for research missions in TraceLab. It provides a structured contract for capturing research objectives, evidence, synthesis, and quality gates.

## Overview

Mission Protocol enables:
- Structured research mission definition
- Evidence tracking with source traceability
- Synthesis of insights from collected evidence
- Quality gates for research rigor validation
- Integration with DeepSearch agents

**Key Reference**: `tracelab_schemas/tracelab_schemas/mission_protocol.py`

---

## Core Schema

### MissionProtocolComplete

The complete mission payload requires all fields for a finished research mission:

```python
class MissionProtocolComplete(BaseModel):
    # Identification
    mission_id: str          # Unique identifier (e.g., "DSR.10.1")
    version: str = "1.0.0"   # Schema version
    title: str               # Required for complete missions
    summary: Optional[str]
    project_id: Optional[str]

    # Status
    status: Literal["review", "complete"] = "complete"
    owner: Optional[str]

    # Core content
    research_statement: ResearchStatement  # Required
    key_questions: List[KeyQuestion]       # At least one answered
    synthesis: Synthesis                   # Required
    evidence: List[Evidence]               # At least one

    # Quality
    quality_checkpoints: List[QualityCheckpoint]

    # Metadata
    tags: List[str]
    discussion_guide: List[str]
    methodology_details: Optional[MethodologyDetails]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
```

---

## Research Statement

Defines the hypothesis and guardrails for a mission:

```python
class ResearchStatement(BaseModel):
    topic: str           # Primary research topic
    objective: str       # Desired business/research outcome
    scope: str           # Boundaries for the research
    audience: Optional[str]       # Intended audience
    methodology: Optional[str]    # Research methodology
    success_metrics: List[str]    # Success signals
    risks: List[str]              # Known risks/assumptions
```

### Example

```json
{
  "topic": "User authentication patterns",
  "objective": "Identify friction points in login flows",
  "scope": "Mobile app users, Q4 2024 sessions",
  "audience": "Product team",
  "methodology": "qualitative interview analysis",
  "success_metrics": [
    "Identify top 3 friction points",
    "Document user workarounds"
  ],
  "risks": [
    "Sample may skew toward power users"
  ]
}
```

---

## Key Questions

Track core research questions through their lifecycle:

```python
class KeyQuestion(BaseModel):
    question: str                           # The research question
    status: KeyQuestionStatus               # "open" | "researching" | "answered"
    answer: Optional[str]                   # Answer (required when answered)
    confidence: Optional[float]             # 0.0-1.0 confidence score
    owner: Optional[str]                    # Question owner
```

### Status Flow

```
open → researching → answered
```

### Validation Rules

- **Answered questions must include an answer**: `status == "answered"` requires non-empty `answer`
- **Confidence range**: Must be between 0.0 and 1.0

### Example

```json
{
  "question": "What causes users to abandon the login flow?",
  "status": "answered",
  "answer": "Primary causes: password complexity (42%), 2FA friction (31%), timeout issues (27%)",
  "confidence": 0.85,
  "owner": "research-team"
}
```

---

## Evidence

Evidence objects link mission findings to source documents:

```python
class Evidence(BaseModel):
    evidence_id: str              # Unique identifier (e.g., "EV-001")
    source: str                   # Source description
    summary: str                  # Evidence summary
    chunk_id: Optional[str]       # TraceLab chunk ID for traceability
    insight_id: Optional[str]     # Associated insight UUID
    source_type: Optional[str]    # interview, survey, log, etc.
    relevance_score: Optional[float]  # 0.0-1.0 relevance
    tags: List[str]
```

### Key Fields

| Field | Purpose |
|-------|---------|
| `evidence_id` | Unique reference within mission |
| `source` | Human-readable source description |
| `chunk_id` | Links to TraceLab document chunk (critical for traceability) |
| `relevance_score` | How relevant this evidence is to the mission |

### Example

```json
{
  "evidence_id": "EV-001",
  "source": "User Interview #12 - Enterprise Admin",
  "summary": "User reported abandoning login after 3 failed 2FA attempts",
  "chunk_id": "f6c9a1b2-3d4e-5f6a-7b8c-9d0e1f2a3b4c",
  "source_type": "interview",
  "relevance_score": 0.91,
  "tags": ["2fa", "friction", "enterprise"]
}
```

---

## Synthesis

Synthesized insights derived from research data:

```python
class Synthesis(BaseModel):
    key_insights: List[str]              # Main findings
    surprising_findings: List[str]       # Unexpected discoveries
    contradictory_information: List[str] # Conflicting data points
    contradiction_resolutions: List[str] # How contradictions were resolved
    recommendations: List[str]           # Actionable recommendations
    next_steps: List[str]                # Follow-up actions
```

### Validation Rules

- **Complete missions must have at least one key insight**

### Example

```json
{
  "key_insights": [
    "Password complexity rules cause 42% of login abandonment",
    "Enterprise users prefer hardware tokens over SMS 2FA",
    "Session timeout under 5 minutes increases support tickets 3x"
  ],
  "surprising_findings": [
    "Users prefer longer passwords with fewer special character requirements"
  ],
  "contradictory_information": [
    "Survey data showed 60% satisfaction with 2FA, but interviews revealed hidden frustration"
  ],
  "contradiction_resolutions": [
    "Survey captured initial sentiment; interviews revealed workarounds users developed"
  ],
  "recommendations": [
    "Extend session timeout to 15 minutes for low-risk actions",
    "Offer passkey as alternative to password+2FA"
  ],
  "next_steps": [
    "A/B test extended session timeout",
    "Prototype passkey integration"
  ]
}
```

---

## Quality Gates

Quality checkpoints enforce research rigor:

```python
class QualityCheckpoint(BaseModel):
    gate: QualityGateName         # Gate identifier
    status: QualityGateStatus     # "pending" | "pass" | "fail"
    notes: Optional[str]          # Evaluation notes
    validated_by: Optional[str]   # Validator identifier
    validated_at: Optional[datetime]
```

### Required Gates for Completion

```python
REQUIRED_COMPLETION_GATES = (
    "research_statement",       # Clear hypothesis defined
    "evidence_links",           # Evidence linked to chunks
    "synthesis_quality",        # Insights derived from evidence
    "traceability",            # Evidence traceable to sources
    "contradictions_resolved",  # Conflicts addressed
)
```

### Gate Definitions

| Gate | Validates |
|------|-----------|
| `research_statement` | Topic, objective, and scope are defined |
| `evidence_links` | Evidence items have chunk_id references |
| `synthesis_quality` | Key insights supported by evidence |
| `traceability` | Full audit trail from insight to source |
| `contradictions_resolved` | Conflicting data points explained |

### Example

```json
{
  "quality_checkpoints": [
    {
      "gate": "research_statement",
      "status": "pass",
      "notes": "Clear topic/scope defined",
      "validated_by": "auto-gate",
      "validated_at": "2024-12-10T14:30:00Z"
    },
    {
      "gate": "evidence_links",
      "status": "pass",
      "notes": "3/3 evidence items linked to chunks",
      "validated_by": "auto-linker"
    }
  ]
}
```

---

## Methodology Details

Operational metadata for quality automation:

```python
class MethodologyDetails(BaseModel):
    participant_segments: List[ParticipantSegment]
    total_participants: Optional[int]
    recruitment_method: Optional[str]
    consent_documented: bool = False
    validation_steps_completed: List[str]
    artifacts_verified: List[str]
    notes: Optional[str]
```

### Participant Segments

```python
class ParticipantSegment(BaseModel):
    segment: str              # Cohort name
    count: Optional[int]      # Number of participants
    percentage: Optional[float]  # 0-1 normalized ratio
```

### Example

```json
{
  "methodology_details": {
    "participant_segments": [
      {"segment": "Enterprise Admin", "count": 8, "percentage": 0.4},
      {"segment": "Individual User", "count": 12, "percentage": 0.6}
    ],
    "total_participants": 20,
    "recruitment_method": "Opt-in from active user pool",
    "consent_documented": true,
    "validation_steps_completed": [
      "Inter-coder reliability check",
      "Member checking with 5 participants"
    ],
    "artifacts_verified": [
      "interview_transcripts/",
      "coding_scheme.xlsx"
    ]
  }
}
```

---

## Mission Lifecycle

### Draft State

```python
class MissionProtocolDraft(MissionProtocolBase):
    """Allows partially filled missions."""
    pass
```

Drafts can omit required fields. Use `draft.promote()` to convert to complete:

```python
draft = MissionProtocolDraft(mission_id="DSR.10.1", ...)
complete = draft.promote()  # Validates all requirements
```

### Complete State

Complete missions are validated for:

1. **Title required**: Non-empty title
2. **Research statement required**: Full statement with topic/objective/scope
3. **Synthesis required**: At least one key insight
4. **Evidence required**: At least one evidence item
5. **Key questions**: At least one answered
6. **Quality gates**: All 5 required gates must pass

---

## Database Storage

Missions are stored with JSON fields for complex structures:

```sql
-- missions table
CREATE TABLE missions (
    id UUID PRIMARY KEY,
    mission_id VARCHAR NOT NULL,  -- Human-readable ID
    title VARCHAR,
    project_id UUID REFERENCES projects(id),
    status VARCHAR,

    -- JSONB columns for protocol data
    research_statement JSONB,
    key_questions JSONB,
    synthesis JSONB,
    evidence JSONB,
    quality_checkpoints JSONB,
    methodology_details JSONB,

    -- Provenance
    evidence_linking_metadata JSONB,

    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

---

## API Integration

### Create Mission

```http
POST /api/v1/missions
Content-Type: application/json

{
  "mission_id": "DSR.10.1",
  "title": "Login Friction Analysis",
  "research_statement": { ... },
  "key_questions": [ ... ],
  "synthesis": { ... },
  "evidence": [ ... ],
  "quality_checkpoints": [ ... ]
}
```

### DeepSearch Ingestion

DeepSearch agents use a dedicated endpoint:

```http
POST /api/v1/deepsearch/ingest
Content-Type: application/json

{
  "project_id": "existing-project-uuid",
  "similarity_threshold": 0.75,
  "mission": { ...MissionProtocolComplete... }
}
```

See [DeepSearch Integration](../integration/deepsearch.md) for details.

---

## Related Documentation

- [PEDR Search Architecture](./PEDR-search.md) - Search layers and fusion
- [DeepSearch Integration](../integration/deepsearch.md) - Agent ingestion patterns
- [Quality Gates](../quality_gates.md) - Gate evaluation details
- [API Overview](../api/README.md) - Full endpoint reference
