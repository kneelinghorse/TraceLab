# DeepSearch ↔ TraceLab Integration Contract

**Date:** 2025-11-16  
**Version:** 1.0 (Draft)  
**Status:** Ready for alignment discussion

---

## Executive Summary

This document defines the integration contract between DeepSearch (autonomous research agent) and TraceLab (knowledge repository). It covers data formats, API endpoints, authentication, error handling, and the integration workflow.

**Key Principle:** DeepSearch generates structured JSON → TraceLab validates and stores → Both systems benefit from quality-enforced knowledge accumulation.

---

## Integration Architecture

```
┌──────────────────────────────────────────┐
│           DeepSearch Agent                │
│  - LangGraph research loops               │
│  - Web search (Tavily/Perplexity)        │
│  - Autonomous synthesis                   │
└──────────┬────────────────────────────────┘
           │
           │ 1. Query existing research
           │    (optional, pre-research check)
           ↓
    ┌──────────────┐
    │ TraceLab API │ ← POST /api/v1/search (via PEDR module)
    │ (Read Mode)  │
    └──────┬───────┘
           │ Returns: missions, documents that already exist
           │
┌──────────┴───────────────────────────────────┐
│         DeepSearch Decision Logic             │
│  - Existing research found? → Skip web search│
│  - No research? → Execute web research loops │
└──────────┬───────────────────────────────────┘
           │
           │ 2. Generate structured output
           │    (Mission Protocol JSON)
           ↓
    ┌──────────────┐
    │ TraceLab API │ ← POST /api/v1/deepsearch/ingest
    │ (Write Mode) │
    └──────┬───────┘
           │ Validates via Pydantic + Quality Gates
           │
           ↓
    [ Stored in PostgreSQL + Qdrant ]
           │
           ↓
    [ PEDR module indexes for future queries ]
```

---

## Phase 1: Simple Integration (Sprint 10 - Recommended Start)

### DeepSearch Output Format

**Simple Markdown Report** (easiest to start):

```markdown
# Research Report: DRM.0.5 - Passwordless Auth Patterns

## Research Statement
**Topic:** Passwordless authentication implementation patterns
**Objective:** Identify proven patterns for web applications
**Scope:** Consumer web apps, 2020-2025 implementations

## Key Questions
1. **Q:** What are the most common passwordless methods?
   **A:** Magic links (45%), WebAuthn (30%), OTP codes (25%)

2. **Q:** What are the security tradeoffs?
   **A:** Magic links = UX simplicity but email compromise risk...

## Key Insights
- Magic links dominate consumer applications due to minimal friction
- WebAuthn adoption increasing for security-critical applications
- OTP codes declining due to SIM-swap vulnerabilities

## Recommendations
1. Use magic links for low-security consumer apps
2. Implement WebAuthn for financial/health applications
3. Consider account recovery flows carefully

## Sources
- https://auth0.com/blog/passwordless-authentication
- https://webauthn.guide/
- User authentication survey 2024
```

**Integration:**
```bash
# Manual upload to TraceLab
tracelab documents upload PROJECT_ID report.md --file-type report --source-type analysis --process
```

**Benefit:** Zero API integration needed, validates end-to-end flow

---

## Phase 2: Structured JSON Integration (Sprint 11+)

### DeepSearch JSON Output Format

**Mission Protocol JSON** (matches `MissionProtocolComplete` schema):

```json
{
  "mission_id": "DRM.0.5",
  "title": "Passwordless Auth Patterns Research",
  "version": "1.0.0",
  "status": "complete",
  "owner": "deepsearch-agent",
  
  "research_statement": {
    "topic": "Passwordless authentication implementation patterns",
    "objective": "Identify proven patterns for web applications",
    "scope": "Consumer web apps, 2020-2025",
    "success_metrics": [
      "Compare at least 3 methods",
      "Document security tradeoffs",
      "Provide implementation guidance"
    ]
  },
  
  "key_questions": [
    {
      "question": "What are the most common passwordless methods?",
      "status": "answered",
      "answer": "Magic links (45%), WebAuthn (30%), OTP codes (25%)",
      "sources": ["https://auth0.com/blog/..."]
    },
    {
      "question": "What are the security tradeoffs?",
      "status": "answered",
      "answer": "Magic links = UX simplicity but email compromise risk...",
      "sources": ["https://webauthn.guide/"]
    }
  ],
  
  "synthesis": {
    "key_insights": [
      "Magic links dominate consumer applications due to minimal friction",
      "WebAuthn adoption increasing for security-critical applications",
      "OTP codes declining due to SIM-swap vulnerabilities"
    ],
    "surprising_findings": [
      "WebAuthn adoption faster in EU than US due to PSD2 requirements"
    ],
    "contradictory_information": [],
    "recommendations": [
      "Use magic links for low-security consumer apps",
      "Implement WebAuthn for financial/health applications"
    ],
    "next_steps": [
      "Prototype WebAuthn flow",
      "Test magic link security edge cases"
    ]
  },
  
  "evidence": [
    {
      "evidence_id": "EV-001",
      "source": "Auth0 Blog - Passwordless Authentication Guide",
      "url": "https://auth0.com/blog/passwordless-authentication",
      "content": "Summary of key points from source...",
      "chunk_id": null
    },
    {
      "evidence_id": "EV-002",
      "source": "WebAuthn Guide",
      "url": "https://webauthn.guide/",
      "content": "WebAuthn provides phishing-resistant authentication...",
      "chunk_id": null
    }
  ],
  
  "quality_checkpoints": [
    {"gate": "research_statement", "status": "pass", "validated_at": "2025-11-16T10:00:00Z"},
    {"gate": "evidence_links", "status": "pass", "validated_at": "2025-11-16T10:00:00Z"},
    {"gate": "synthesis_quality", "status": "pass", "validated_at": "2025-11-16T10:00:00Z"},
    {"gate": "traceability", "status": "pass", "validated_at": "2025-11-16T10:00:00Z"},
    {"gate": "contradictions_resolved", "status": "pass", "validated_at": "2025-11-16T10:00:00Z"}
  ],
  
  "tags": ["authentication", "security", "passwordless", "webauthn"],
  "created_at": "2025-11-16T10:00:00Z"
}
```

### TraceLab Ingestion Endpoint

**POST /api/v1/deepsearch/ingest** (to be built in Sprint 10)

**Request Headers:**
```
Authorization: Bearer {jwt_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "project_id": "uuid-or-null",
  "mission": { ...MissionProtocolComplete JSON... },
  "auto_create_project": true,
  "project_name": "DeepSearch Research Output"
}
```

**Success Response (201 Created):**
```json
{
  "mission_id": "uuid-generated-by-tracelab",
  "status": "complete",
  "quality_gates": {
    "research_statement": "pass",
    "evidence_links": "pass",
    "synthesis_quality": "pass",
    "traceability": "pass",
    "contradictions_resolved": "pass"
  },
  "created_at": "2025-11-16T10:00:00Z"
}
```

**Validation Error Response (422):**
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "mission", "synthesis", "key_insights"],
      "msg": "Synthesis must include at least one key insight.",
      "input": []
    }
  ]
}
```

**Quality Gate Failure (400):**
```json
{
  "success": false,
  "error": {
    "code": "QUALITY_GATE_FAILURE",
    "message": "Mission validation failed - quality gates not passed",
    "details": {
      "failing_gates": ["evidence_links", "traceability"],
      "mission_id": "DRM.0.5",
      "suggestions": [
        "Add at least one evidence item with chunk_id",
        "Ensure all evidence has source references"
      ]
    }
  }
}
```

---

## DeepSearch Requirements for TraceLab

### 1. Before You Start Research

**Query TraceLab:** "Does this research already exist?"

**Endpoint:** `POST /api/v1/search` (existing, enhanced with PEDR in Sprint 10)

**Request:**
```json
{
  "query": "passwordless authentication patterns",
  "search_mode": "hybrid",
  "top_k": 10,
  "filters": {
    "min_quality_gates": 4,
    "status": ["complete"],
    "allow_pii": false
  }
}
```

**Response:**
```json
{
  "results": [
    {
      "chunk_id": "uuid",
      "content": "Magic links are the most popular...",
      "score": 0.89,
      "document": {
        "id": "uuid",
        "name": "Auth Patterns Report",
        "file_type": "report"
      },
      "mission": {
        "id": "uuid",
        "mission_id": "DRM.0.3",
        "title": "Authentication Methods Research",
        "status": "complete",
        "quality_gates_passed": 5
      }
    }
  ],
  "total": 3
}
```

**Decision Logic:**
- **If results found:** Summarize existing research, skip web search
- **If no results:** Proceed with autonomous web research

---

### 2. After Research Complete

**Send Structured Output to TraceLab**

**Endpoint:** `POST /api/v1/deepsearch/ingest` (Sprint 10)

**Critical Fields for Quality Gates:**
- ✅ `research_statement` fully populated (topic, objective, scope)
- ✅ At least 1 answered key question
- ✅ `synthesis.key_insights[]` non-empty (≥1 insight, ≥40 chars each)
- ✅ `synthesis.recommendations[]` non-empty (≥1 recommendation)
- ✅ `synthesis.next_steps[]` non-empty (≥1 next step)
- ✅ `evidence[]` non-empty (≥1 evidence item)
- ✅ All 5 quality checkpoints with `status: "pass"`
- ✅ No unresolved contradictions

**Optional but Recommended:**
- Tags for categorization
- URLs in evidence sources
- Timestamps (created_at, updated_at)

---

### 3. Error Handling

**DeepSearch Should Handle:**

**422 Validation Errors:**
```python
response = tracelab_api.post("/deepsearch/ingest", json=mission_data)

if response.status_code == 422:
    errors = response.json()["detail"]
    # Log errors for debugging
    logger.error(f"TraceLab validation failed: {errors}")
    
    # Option A: Log and continue (no retry)
    # Option B: Trigger correction loop (Sprint 11 feature)
```

**400 Quality Gate Failures:**
```python
if response.status_code == 400:
    failing_gates = response.json()["error"]["details"]["failing_gates"]
    # Log which gates failed
    logger.error(f"Quality gates failed: {failing_gates}")
    
    # For MVP: Log and continue
    # Future: Refine research to fix gates
```

---

## Authentication

### Service Account Setup

**Step 1: Create DeepSearch Service Account** (in TraceLab)
```bash
# TraceLab admin creates service account
tracelab auth create-service-account "deepsearch-agent" --role agent
# Returns: username + password
```

**Step 2: DeepSearch Login**
```python
# In DeepSearch initialization
response = requests.post(
    "http://localhost:8000/api/v1/auth/login",
    json={"username": "deepsearch-agent", "password": "..."}
)
token = response.json()["access_token"]

# Store in environment
os.environ["TRACELAB_TOKEN"] = token
```

**Step 3: Use Token in Requests**
```python
headers = {"Authorization": f"Bearer {os.environ['TRACELAB_TOKEN']}"}
requests.post("http://localhost:8000/api/v1/deepsearch/ingest", json=data, headers=headers)
```

---

## Open Questions for Alignment

### 1. Project Management

**Question:** How does DeepSearch specify which TraceLab project to write to?

**Options:**
- A) Use single default project (simplest)
- B) DeepSearch creates new project per research domain
- C) User pre-creates projects, DeepSearch maps via config

**Recommendation:** Start with A (default project), add B in Phase 2

---

### 2. Chunking Strategy

**Question:** Who handles chunking - DeepSearch or TraceLab?

**Current Plan:** TraceLab auto-chunks markdown uploads

**DeepSearch Provides:**
- Markdown report (full text)
- Optional: pre-chunked sections if helpful

**TraceLab Handles:**
- Chunking (500-1000 tokens, 50 overlap)
- Embedding generation (OpenAI text-embedding-3-small)
- Qdrant storage

**Benefit:** Consistent chunking across all documents

---

### 3. Evidence Linking

**Question:** How does DeepSearch reference chunks it doesn't create?

**Problem:** DeepSearch doesn't have chunk IDs (TraceLab generates them)

**Solutions:**

**Option A: URL-based references** (Simple, recommended for Phase 1)
```json
{
  "evidence": [
    {
      "evidence_id": "EV-001",
      "source": "Auth0 Blog",
      "url": "https://auth0.com/blog/passwordless",
      "content": "Summary of key points...",
      "chunk_id": null
    }
  ]
}
```
TraceLab stores without chunk linking initially.

**Option B: Two-phase ingestion** (Phase 2)
```
1. DeepSearch POSTs markdown → TraceLab chunks it
2. TraceLab returns chunk IDs
3. DeepSearch POSTs mission referencing chunk IDs
```

**Option C: Post-processing** (Phase 2)
```
1. DeepSearch POSTs complete mission (no chunk refs)
2. TraceLab background job matches evidence text to chunks
3. Auto-links evidence to chunks via similarity
```

**Recommendation:** Start with Option A (URL-only evidence), add chunk linking in Phase 2

---

### 4. Error Correction Loop

**Question:** Should 422/400 errors trigger automatic refinement?

**Phase 1 (MVP):** No auto-correction
- Log errors
- Human reviews failed submissions
- Manual iteration

**Phase 2:** Correction loop (Sprint 11)
- 422 errors → extract missing fields
- Trigger DeepSearch refinement pass
- Retry submission
- Max 2 retries

**Phase 3:** Smart correction
- Analyze error patterns
- Pre-validate before submission
- Confidence scoring

**Recommendation:** Phase 1 for MVP, iterate based on error frequency

---

### 5. PEDR Query Integration

**Question:** When should DeepSearch query PEDR?

**Options:**

**A) Pre-Research Check** (Recommended)
```python
# Before starting web search
existing = tracelab_api.post("/api/v1/search", json={
    "query": mission_objective,
    "filters": {"status": ["complete"], "min_quality_gates": 4}
})

if existing["total"] > 0:
    # Use existing research, skip web search
    return summarize_existing(existing["results"])
```

**B) During Research** (Optional)
- Query at each research loop
- Blend internal + external sources
- More complex logic

**C) Never** (Simplest)
- DeepSearch always researches externally
- TraceLab accumulates knowledge
- Manual discovery of duplicates

**Recommendation:** Start with A (pre-research check), simplest implementation with high value

---

## Sprint 10 Deliverables (TraceLab Side)

### B10.1: Quality-Aware Search (PEDR Phase 1)
- Extend HybridSearchService with quality boosting
- Complete missions rank 2× higher
- Governance filters (min_quality_gates, allow_pii)

### B10.2: DeepSearch Ingestion Endpoint
- `POST /api/v1/deepsearch/ingest`
- Accepts Mission Protocol JSON
- Validates + stores
- Returns mission UUID

### B10.3: Relationship Context API
- `GET /api/v1/missions/{id}/related`
- Returns linked documents, insights, chunks
- Simple SQL joins (no graph DB)

### B10.4: Integration Testing
- End-to-end test suite
- Mock DeepSearch outputs
- Validate all error cases

### B10.5: Sprint Retrospective
- Standard closer

---

## Sprint 10 Requirements (DeepSearch Side)

### Coordinate With TraceLab Team:

1. **Output Format Decision**
   - Start with markdown or jump to JSON?
   - If JSON: review Mission Protocol schema

2. **Authentication Setup**
   - Get service account credentials
   - Implement JWT token flow

3. **Error Handling**
   - Plan for 422/400 responses
   - Log errors for Phase 2 correction loop

4. **Testing**
   - Provide sample research outputs
   - Test against TraceLab staging

---

## Success Criteria for Integration

**Phase 1 Complete When:**
- ✅ DeepSearch can POST research to TraceLab
- ✅ TraceLab validates and stores successfully
- ✅ Quality gates enforce structure
- ✅ DeepSearch can query before researching (optional)
- ✅ End-to-end test passes

**Metrics:**
- Integration latency <1 second
- Validation success rate >90%
- Zero data loss

---

## Timeline

**Sprint 10** (TraceLab): 2 weeks
- PEDR Phase 1 (quality search)
- Ingestion endpoint
- Integration testing

**DeepSearch Coordination:** Parallel work
- Finalize JSON output format
- Implement TraceLab client
- Test integration

**Integration Testing:** End of Sprint 10
- Both teams coordinate
- End-to-end validation
- Iterate on issues

---

## Next Steps

1. **DeepSearch Team:** Review this contract
2. **Both Teams:** Align on Phase 1 approach (markdown vs JSON)
3. **TraceLab:** Start Sprint 10 missions
4. **DeepSearch:** Implement client for chosen format
5. **Week 2:** Integration testing session

---

## Questions for DeepSearch Team

1. **Preferred start:** Markdown (simple) or JSON (structured)?
2. **Project handling:** Single project or auto-create?
3. **Authentication:** Ready to implement JWT flow?
4. **Timeline:** Can coordinate integration testing in 2 weeks?
5. **Pre-research query:** Want to check TraceLab before web search?

**Next:** Sync meeting or async via planning docs

---

**Status:** Ready for alignment discussion  
**Owner:** TraceLab team  
**Contact:** Via `cmos/planning/` updates

