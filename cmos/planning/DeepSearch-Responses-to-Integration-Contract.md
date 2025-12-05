# DeepSearch Responses to Integration Contract

**Date:** 2025-11-17  
**Status:** Answering TraceLab's integration questions  
**Reference:** DeepSearch-TraceLab-Integration-Contract.md v1.0

---

## Answers to "Questions for DeepSearch Team"

### 1. **Preferred start:** Markdown (simple) or JSON (structured)?

**Answer: Start with Markdown (Phase 1), progress to JSON (Phase 2-3)**

**Rationale:**
- **Sprint 1-2 (Standalone MVP):** Markdown only output to `cmos/research/`. No TraceLab integration.
- **Sprint 3 (Semi-automated):** Dual output (Markdown + JSON). Human uploads markdown via CLI, we validate JSON locally.
- **Sprint 4+ (Automated):** JSON ingestion via `POST /api/v1/deepsearch/ingest`

**Recommendation:** TraceLab should prioritize **markdown upload endpoint** first (`POST /api/v1/documents/upload`), then build **JSON ingestion endpoint** (`POST /api/v1/deepsearch/ingest`) in Sprint 10-11.

**This phased approach allows:**
- ✅ DeepSearch to validate Mission-as-State pattern independently (Sprint 1-2)
- ✅ TraceLab to validate chunking/embedding pipeline with manual uploads (Sprint 10)
- ✅ Both teams to test end-to-end before full automation (Sprint 11)

---

### 2. **Project handling:** Single project or auto-create?

**Answer: Config-based mapping with auto-create fallback (Option C + B hybrid)**

**Implementation Plan:**

**Config File:** `deepsearch/config/tracelab_projects.yaml`
```yaml
projects:
  DRM:  # Mission prefix
    project_id: "uuid-if-known"  # null initially
    project_name: "DeepSearch Research Missions"
    auto_create: true
  
  # Future research domains
  PERF:
    project_id: null
    project_name: "Performance Research"
    auto_create: true
```

**Workflow:**
1. DeepSearch reads mission ID (e.g., `DRM.0.5`)
2. Checks config for `DRM` → finds `project_id`
3. If `project_id` is null:
   - Query TraceLab: `GET /api/v1/projects?name=DeepSearch+Research+Missions`
   - If exists: Cache UUID in config
   - If not: `POST /api/v1/projects` with `auto_create_project: true`
4. Use project_id in mission ingestion

**Benefit:** Flexibility to pre-create projects (TraceLab side) OR auto-create (DeepSearch side)

---

### 3. **Authentication:** Ready to implement JWT flow?

**Answer: Yes, ready to implement - but need coordination on service account creation**

**Our Requirements:**
1. **Service account credentials** from TraceLab team
   - Username: `deepsearch-agent`
   - Password: (provided securely)
   - Role: `agent` (or appropriate role)

2. **Token management strategy:**
   - Store credentials in `.env` file (not version controlled)
   - Implement token caching (24h expiry)
   - Auto-refresh on 401 responses

**Implementation Timeline:**
- **Sprint 3:** Implement JWT client, test against TraceLab staging
- **Sprint 4:** Production authentication, error handling

**Need from TraceLab:**
- Service account creation guide or CLI command
- Token expiry policy (24h confirmed?)
- Refresh token support or re-login required?

---

### 4. **Timeline:** Can coordinate integration testing in 2 weeks?

**Answer: Not in 2 weeks - our Sprint 1-2 (4 weeks) focused on standalone mode**

**Our Timeline:**
- **Sprint 1-2 (Weeks 1-4):** Standalone DeepSearch MVP
  - LangGraph agent with research loops
  - Markdown report generation
  - No TraceLab integration
  
- **Sprint 3 (Weeks 5-6):** TraceLab prep
  - JSON payload generation
  - Local Pydantic validation
  - Integration client implementation
  
- **Sprint 4 (Weeks 7-8):** Live integration
  - Automated upload to TraceLab
  - Error handling
  - **Integration testing coordination** ← Best window

**Recommendation:** Schedule integration testing for **Week 7** (Sprint 4 start), giving both teams runway to build independently first.

**Can we do earlier validation?**
- Week 4: DeepSearch can provide **sample JSON outputs** for TraceLab schema validation
- Week 6: DeepSearch can test against TraceLab staging with **manual uploads**

---

### 5. **Pre-research query:** Want to check TraceLab before web search?

**Answer: Yes, but deferred to Sprint 5 (PEDR integration phase)**

**Rationale:**
- **Sprint 1-4:** Focus on "write path" (DeepSearch → TraceLab)
- **Sprint 5:** Add "read path" (PEDR query before research)

**Implementation Plan (Sprint 5):**
```python
# Before research loops
existing_research = tracelab_api.post("/api/v1/search", json={
    "query": mission_objective,
    "search_mode": "hybrid",
    "filters": {
        "status": ["complete"],
        "min_quality_gates": 4
    }
})

if existing_research["total"] > 0 and max(r["score"] for r in existing_research["results"]) > 0.8:
    # High relevance found - present to user
    logger.info(f"Found {existing_research['total']} existing research items")
    # Option: Skip web search, use existing
    # Option: Augment with new web search
else:
    # No existing research - proceed with web search
    proceed_with_web_research()
```

**Decision point:** Should DeepSearch automatically skip web search if high-relevance internal research exists, or always present choice to user?

**Recommendation:** Start with **automatic skip** if relevance >0.9, **user prompt** if 0.7-0.9, **proceed with web search** if <0.7

---

## Responses to "Open Questions for Alignment"

### 1. Project Management

**DeepSearch Position:** Hybrid approach (Option C + B)

- Config-based mapping for known domains (DRM, PERF, etc.)
- API fallback with auto-create for new domains
- Caching of project UUIDs to avoid repeated lookups

**Aligns with TraceLab's Option B recommendation**

---

### 2. Chunking Strategy

**DeepSearch Position:** TraceLab owns all chunking (100% agreement)

**DeepSearch Responsibilities:**
- Generate markdown report (single file, well-structured)
- Provide clear section headers (## for chunking hints)
- No pre-chunking, no chunk management

**TraceLab Responsibilities:**
- Chunk markdown (500-1000 tokens, 50 overlap)
- Generate embeddings
- Store in Qdrant
- Return chunk IDs for mission evidence linking

**Critical:** DeepSearch does NOT create `DocumentChunk` objects

---

### 3. Evidence Linking

**DeepSearch Position: Start with Option A (URL-only), migrate to Option B (two-phase) in Sprint 4**

**Phase 1 (Sprint 3):**
```json
{
  "evidence": [
    {
      "evidence_id": "EV-001",
      "source": "Auth0 Blog",
      "url": "https://auth0.com/blog/passwordless",
      "content": "Summary of key points from source...",
      "chunk_id": null  // No chunk reference initially
    }
  ]
}
```

**Phase 2 (Sprint 4 - Two-phase ingestion):**
```
1. POST /api/v1/documents/upload (markdown report)
   → Returns document_id
2. POST /api/v1/documents/{document_id}/process
   → Triggers chunking (async)
3. Poll GET /api/v1/documents/{document_id}/status
   → Wait for processed: true
4. GET /api/v1/documents/{document_id}/chunks
   → Returns chunk UUIDs
5. POST /api/v1/deepsearch/ingest (mission with chunk refs)
```

**Question for TraceLab:** Is two-phase ingestion feasible, or should we go straight to Option C (post-processing auto-linking)?

**Preference:** Two-phase gives DeepSearch control over evidence→chunk mapping, but post-processing is simpler.

---

### 4. Error Correction Loop

**DeepSearch Position: Phase 1 (MVP) - no auto-correction**

**Sprint 3-4 Implementation:**
```python
response = tracelab_api.post("/api/v1/deepsearch/ingest", json=mission_data)

if response.status_code == 422:
    errors = response.json()["detail"]
    logger.error(f"Validation failed: {errors}")
    
    # Save to failed submissions directory
    save_failed_submission(
        payload=mission_data,
        errors=errors,
        path=f"cmos/research/failed_submissions/{mission_id}.json"
    )
    
    return {
        "status": "validation_failed",
        "error_log": f"failed_submissions/{mission_id}.json"
    }

if response.status_code == 400:
    failing_gates = response.json()["error"]["details"]["failing_gates"]
    logger.error(f"Quality gates failed: {failing_gates}")
    
    # Same: log and save for manual review
```

**Sprint 5+ (Correction Loop):**
- Analyze error patterns
- Trigger LLM refinement pass
- Max 2 retry attempts
- Learn from corrections

**Aligns with TraceLab's Phase 1 recommendation**

---

### 5. PEDR Query Integration

**DeepSearch Position: Option A (Pre-Research Check) - deferred to Sprint 5**

**Workflow:**
```python
# Sprint 5 implementation
async def execute_research_mission(mission: Mission):
    # Step 1: Check existing research
    if config.ENABLE_PEDR_CHECK:
        existing = await query_tracelab_pedr(mission.objective)
        
        if existing["total"] > 0:
            best_match = existing["results"][0]
            if best_match["score"] > 0.9:
                logger.info(f"High-relevance match found: {best_match['mission']['title']}")
                # Skip web search, use existing
                return synthesize_existing_research(existing["results"])
            elif best_match["score"] > 0.7:
                # Prompt user: use existing or proceed?
                user_choice = await prompt_user_decision(best_match)
                if user_choice == "use_existing":
                    return synthesize_existing_research(existing["results"])
    
    # Step 2: Proceed with web research
    return await execute_web_research_loops(mission)
```

**Aligns with TraceLab's Option A recommendation**

---

## Architecture Update: PEDR as TraceLab Module

**Important Change:** PEDR is now part of TraceLab (not separate service)

**This simplifies our architecture:**

**Old (3-service):**
```
DeepSearch → TraceLab → PEDR (separate service)
```

**New (2-service):**
```
DeepSearch → TraceLab (includes PEDR module)
```

**Benefits:**
- ✅ Single API endpoint (`/api/v1/search` with PEDR enhancements)
- ✅ No separate service authentication
- ✅ Simpler deployment
- ✅ TraceLab owns indexing workflow

**Impact on DeepSearch:**
- No change to implementation (same API contract)
- Simplified architecture documentation
- One less dependency to manage

---

## Open Issues - RESOLVED ✅

### Issue 1: Two-Phase Ingestion Complexity ✅

**Question:** Is two-phase workflow (upload → process → get chunks → submit mission) manageable, or should we use post-processing auto-linking (Option C)?

**DECISION: Post-processing (Option C)**

**DeepSearch Position:**
- Use post-processing auto-linking
- TraceLab handles the complexity of matching evidence to chunks
- DeepSearch submits mission with URL-based evidence only
- TraceLab background job links evidence to chunks via similarity matching

**Implementation:**
```json
{
  "evidence": [
    {
      "evidence_id": "EV-001",
      "source": "Auth0 Blog",
      "url": "https://auth0.com/blog/passwordless",
      "content": "Brief summary of key points (1-2 sentences)",
      "chunk_id": null  // TraceLab fills this via background job
    }
  ]
}
```

**Benefit:** Simpler for DeepSearch, TraceLab controls chunking and linking logic consistently

---

### Issue 2: Evidence Content Field ✅

**Question:** Should `evidence[].content` be a full quote or a brief summary?

**DECISION: Brief summary (1-2 sentences)**

**Implementation:**
- DeepSearch generates concise summaries for each evidence item
- Format: 1-2 sentences capturing key point from source
- Full content preserved in chunks (TraceLab's responsibility)

**Example:**
```json
{
  "evidence_id": "EV-001",
  "source": "Auth0 Blog - Passwordless Auth Guide",
  "url": "https://auth0.com/blog/passwordless",
  "content": "Magic links dominate consumer apps with 45% adoption. Email compromise remains the primary security concern."
}
```

**Benefit:** Easier for LLM to generate, sufficient for evidence traceability

---

### Issue 3: Quality Checkpoints Pre-validation ✅

**Question:** Should DeepSearch run quality gate checks locally before submitting?

**DECISION: Pre-validate using shared Pydantic schemas (Option B)**

**Request to TraceLab:**
- Expose Pydantic schemas as importable Python package
- Options:
  - Publish to private PyPI
  - Git submodule
  - Shared Python package in repo

**Implementation (DeepSearch side):**
```python
from tracelab_schemas import MissionProtocolComplete

# Validate before submission
try:
    mission = MissionProtocolComplete(**mission_data)
    # Pre-validation passed, proceed with API call
    response = tracelab_api.post("/api/v1/deepsearch/ingest", json=mission.model_dump())
except ValidationError as e:
    # Fix locally before submission
    logger.error(f"Pre-validation failed: {e}")
```

**Benefit:** Catch errors early, reduce 422 responses, faster iteration

**Action Item for TraceLab:** Provide schema package by Sprint 3 (Week 5)

---

### Issue 4: Token Refresh Strategy ✅

**Question:** How does TraceLab handle expired tokens?

**DECISION: 24-hour token expiry with retry-on-401**

**Token Policy:**
- JWT tokens valid for 24 hours
- No proactive refresh needed (research missions complete in <1 hour)
- On 401 Unauthorized: re-authenticate and retry

**Implementation (DeepSearch side):**
```python
class TraceLab APIClient:
    def __init__(self):
        self.token = None
        self.token_expires_at = None
    
    async def request(self, method, endpoint, **kwargs):
        # Ensure we have valid token
        if not self.token or datetime.now() > self.token_expires_at:
            await self._authenticate()
        
        response = await self.session.request(method, endpoint, **kwargs)
        
        # Handle token expiry
        if response.status_code == 401:
            logger.info("Token expired, re-authenticating...")
            await self._authenticate()
            response = await self.session.request(method, endpoint, **kwargs)
        
        return response
    
    async def _authenticate(self):
        response = await self.session.post("/api/v1/auth/login", json={
            "username": os.environ["TRACELAB_USERNAME"],
            "password": os.environ["TRACELAB_PASSWORD"]
        })
        self.token = response.json()["access_token"]
        self.token_expires_at = datetime.now() + timedelta(hours=24)
```

**Benefit:** Simple retry logic, no complex refresh token handling

---

### Issue 5: Integration Testing Timeline Alignment ✅

**Question:** Can we schedule a joint integration testing session?

**DECISION: Confirmed timeline with flexible coordination**

**Integration Testing Schedule:**
- **Week 4 (End Sprint 2):** DeepSearch provides sample JSON outputs for schema validation
- **Week 6 (End Sprint 3):** DeepSearch tests manual uploads to TraceLab staging
- **Week 7 (Sprint 4 start):** Live integration testing with automated upload
- **Week 8:** Bug fixes, refinement, production validation

**Coordination Commitment:**
- DeepSearch team will orchestrate testing sessions as needed
- Flexible scheduling to align with TraceLab Sprint 10-11 availability
- Async communication via `cmos/planning/` updates
- Sync meetings scheduled as needed for complex issues

**Deliverables by Phase:**
- Week 4: 3-5 sample JSON payloads representing different research types
- Week 6: Test results from manual uploads (success/error cases)
- Week 7: Automated integration test suite results
- Week 8: Production readiness checklist

**Benefit:** Phased validation reduces risk, allows both teams to iterate independently

---

## DeepSearch Deliverables by Phase

### Sprint 1-2 (Standalone MVP)
- ✅ LangGraph research agent
- ✅ Markdown report generation
- ✅ No TraceLab integration
- **Output:** Sample markdown reports for TraceLab review

### Sprint 3 (Integration Prep)
- ✅ JSON payload generation (MissionProtocolComplete format)
- ✅ Local Pydantic validation
- ✅ TraceLab API client (JWT auth)
- ✅ Manual upload CLI script
- **Output:** JSON payloads for TraceLab schema validation

### Sprint 4 (Automated Integration)
- ✅ Automated upload post-research
- ✅ Two-phase or post-processing workflow (TBD with TraceLab)
- ✅ Error handling (422/400 logging)
- ✅ Integration testing with TraceLab team
- **Output:** Production-ready integration

### Sprint 5 (PEDR Integration)
- ✅ Pre-research query to TraceLab PEDR
- ✅ Relevance-based decision logic
- ✅ Full virtuous knowledge loop
- **Output:** Complete autonomous knowledge system

---

## Action Items for DeepSearch

- [ ] Update architecture docs: PEDR is now part of TraceLab (not separate)
- [ ] Create sample JSON payloads by end of Sprint 2
- [ ] Implement JWT client in Sprint 3
- [ ] Coordinate integration testing window with TraceLab (Week 7)
- [ ] Define error handling strategy for failed submissions

---

## Action Items for TraceLab

- [x] ~~Confirm two-phase ingestion vs post-processing approach~~ → **Post-processing chosen**
- [x] ~~Clarify evidence content expectations~~ → **Brief summaries (1-2 sentences)**
- [x] ~~Decision on sharing Pydantic schemas~~ → **Yes, provide as importable package by Sprint 3**
- [x] ~~Document token refresh flow~~ → **24-hour JWT with retry-on-401**
- [x] ~~Confirm integration testing timeline~~ → **Week 4/6/7/8 schedule confirmed**
- [ ] **NEW: Expose Pydantic schemas as Python package** (by Week 5 / Sprint 3 start)
- [ ] **NEW: Implement post-processing auto-linking for evidence→chunks** (Sprint 10)
- [ ] **NEW: Document post-processing matching algorithm** (similarity threshold, confidence scoring)
- [ ] Provide service account creation instructions (by Week 5 / Sprint 3 start)

---

## Summary

**Alignment Level:** 100% aligned ✅

**All Decisions Made:**
- ✅ Start with markdown, progress to JSON
- ✅ TraceLab handles all chunking
- ✅ Config-based project mapping with auto-create
- ✅ JWT authentication ready to implement (24-hour tokens)
- ✅ No auto-correction in Phase 1
- ✅ PEDR pre-check in Sprint 5
- ✅ **Post-processing for evidence→chunk linking**
- ✅ **Brief summaries for evidence content**
- ✅ **Pre-validation using shared Pydantic schemas**
- ✅ **24-hour JWT tokens with retry-on-401**
- ✅ **Integration testing Week 4/6/7/8**

**Ready to Build:**
- DeepSearch: Sprint 1-2 standalone, Sprint 3-4 integration
- TraceLab: Sprint 10 ingestion endpoint + post-processing
- Integration: Week 7 joint testing

**Next Step:** TraceLab implements Sprint 10 missions, DeepSearch builds MVP

---

**Date:** 2025-11-17  
**Status:** Ready for TraceLab review  
**Contact:** Via `cmos/planning/` updates

