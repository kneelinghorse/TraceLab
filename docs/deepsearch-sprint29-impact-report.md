# DeepSearch Sprint 29 Impact Report

**Sprint**: 29 — Search Stack Modernization & Agent Experience
**Date**: March 2026
**Audience**: DeepSearch integration team
**Purpose**: Document all Sprint 29 changes that affect DeepSearch agents querying TraceLab, with actionable migration steps.

---

## Table of Contents

1. [LLM Model Migration](#1-llm-model-migration-gpt-4o--gpt-5x)
2. [Embedding Model & Dimension Upgrade](#2-embedding-model--dimension-upgrade)
3. [PEDR Search Quality Improvements](#3-pedr-search-quality-improvements)
4. [Evidence Auto-Linking Upgrade](#4-evidence-auto-linking-upgrade-difflib--embeddings)
5. [API Endpoint Changes](#5-api-endpoint-changes)
6. [Optimization Recommendations](#6-optimization-recommendations-for-deepsearch-agents)
7. [Migration Checklist](#7-migration-checklist)

---

## 1. LLM Model Migration (GPT-4o → GPT-5.x)

### What Changed

Both deprecated OpenAI chat models have been replaced:

| Role | Previous Model | New Model | Retirement Date |
|------|---------------|-----------|-----------------|
| Primary (RAG synthesis) | `gpt-4o-mini` | `gpt-5.1` | ~Feb 27, 2026 |
| Escalation (complex queries) | `gpt-4o` | `gpt-5.2` | ~Feb 16, 2026 |

**Configuration defaults** (`app/core/config.py`):
- `openai_chat_model` = `"gpt-5.1"`
- `openai_escalation_model` = `"gpt-5.2"`

**Pricing update** (`app/services/cost_monitor.py`):

| Model | Prompt (per 1K tokens) | Completion (per 1K tokens) |
|-------|----------------------:|---------------------------:|
| gpt-5.1 | $0.00125 | $0.01000 |
| gpt-5.2 | $0.00200 | $0.01600 |

**Behavioral changes**:
- GPT-5.x requests now include `reasoning_effort='none'` so that `temperature` and `max_tokens` parameters remain valid (GPT-5 models default to reasoning mode otherwise).
- Tiered routing escalation logic unchanged — low-quality primary responses still trigger escalation to `gpt-5.2`.
- Quality assessment refusal detection extended to catch `"can't assist"` phrasing patterns from GPT-5.x outputs.

### Why It Matters for DeepSearch

- RAG synthesis responses may differ in style/structure from GPT-4o outputs. If DeepSearch agents parse synthesis responses structurally (beyond plain text), test against GPT-5.x output patterns.
- Cost per query changes. The pricing table above reflects the new per-token rates for budget tracking.
- The `reasoning_effort='none'` parameter is set server-side; DeepSearch agents do not need to pass it.

### What DeepSearch Needs to Do

- **No code changes required** — model selection is server-side configuration.
- **Test response parsing**: If agents parse RAG response structure beyond plain text, validate against GPT-5.x outputs.
- **Update cost estimates**: Use the new pricing for any internal cost tracking.

---

## 2. Embedding Model & Dimension Upgrade

### What Changed

| Parameter | Previous | New |
|-----------|----------|-----|
| Model | `text-embedding-3-small` | `text-embedding-3-large` |
| Dimensions | 1536 | 3072 |
| Cost | $0.02/M tokens | $0.13/M tokens |
| Collection name | `research_chunks` | `research_chunks_v2_3072d` |

**Configuration** (`app/core/config.py`, `.env.example`):
- `openai_embedding_model` = `"text-embedding-3-large"`
- `openai_embedding_dimension` = `3072`
- `QDRANT_COLLECTION_NAME` = `"research_chunks_v2_3072d"` (env override)

**Benchmark results** (13,068 chunks, 150 queries, top_k=5):

| Metric | 1536d (small) | 3072d (large) | Delta |
|--------|-------------:|-------------:|------:|
| Precision@5 | 0.5573 | 0.5840 | +4.8% |
| Recall@5 | 0.9467 | 0.9200 | -2.8% |
| nDCG@5 | 0.8715 | 0.8579 | -1.6% |
| Latency P95 | 55.9ms | 131.3ms | +75.4ms |
| Latency P99 | 68.4ms | 142.6ms | +74.2ms |

HNSW parameter sweep confirmed P99 <= 71.6ms with recall=1.0 across ef values [48, 64, 96, 128]. P95 remains well under the 200ms target.

**Infrastructure changes**:
- New Qdrant collection `research_chunks_v2_3072d` with 3072-dimensional vectors, COSINE distance
- Semantic cache collection recreated at 3072 dimensions
- INT8 scalar quantization re-applied at 0.99 quantile
- HNSW parameters: m=16, ef_construct=100, ef_search=64

### Why It Matters for DeepSearch

This is the **highest-impact change** for DeepSearch. Any system that generates its own embeddings for TraceLab queries must match the new model and dimensionality, or similarity scores will be meaningless.

### What DeepSearch Needs to Do

- **Critical**: If DeepSearch generates embeddings client-side for any purpose (pre-filtering, caching, similarity checks), switch to `text-embedding-3-large` with `dimensions=3072`.
- **Update any hardcoded dimension assumptions**: Any code referencing 1536 dimensions must change to 3072.
- **Re-calibrate similarity thresholds**: Score distributions shift with the new model. Cosine similarity values from `text-embedding-3-large` are not directly comparable to `text-embedding-3-small` scores.
- **Note latency increase**: P95 search latency increased from ~56ms to ~131ms. Still under 200ms, but factor into timeout budgets.
- **No re-indexing needed on DeepSearch side**: TraceLab has already re-embedded all 13,068 chunks.

---

## 3. PEDR Search Quality Improvements

### What Changed

Sprint 29 fixed 25+ bugs across the PEDR (Protocol for Evidence-Driven Retrieval) stack, split across two missions:

#### T29.3 — Protocol Layer Fixes (Semantic, Syntactic, Pragmatic, Quality, Relational, Graph)

**Critical fix — Score Compounding (BUG-6/9)**:
Previously, syntactic, pragmatic, and quality layers multiplicatively compounded `combined_score`, meaning each layer read the already-boosted score from the previous layer. This could inflate scores by up to **1.99x** or deflate to **0.1x**.

**New score fusion model** (`app/services/pedr/score_utils.py`):
```
fused_score = base_score * (1.0 + type_boost + intent_boost) * quality_multiplier
```
- Each layer's boost is applied against the **original base score** independently
- A new `score_fusion` metadata block is included in results showing the breakdown:
  - `base_score`: Original RRF/semantic score before any boosts
  - `type_boost`: Syntactic element-type boost
  - `intent_boost`: Pragmatic intent-match boost
  - `additive_boost_factor`: Combined `(1 + type_boost + intent_boost)`
  - `quality_multiplier`: Quality gates multiplier

**Other protocol fixes**:
- Quality score zero-override fixed: Results with 0 quality gates no longer promoted from 0.0 to 0.60 (was a falsy `or` bug)
- Graph layer BFS now uses a global visited set, preventing exponential traversal
- Intent resolution uses confidence scoring instead of first-match dictionary iteration
- Blast radius normalization consistent across both semantic protocol locations
- Session leak in relational layer fixed via context-managed DB sessions
- Dead code removed (EdgeDirection enum, RelationshipsV33, unused imports)

#### T29.4 — Orchestrator & Cache Fixes

**Critical fix — Cache Poisoning (BUG-5)**:
Cache key was missing layer enable flags (`enable_lexical`, `enable_semantic`, `enable_syntactic`, `enable_pragmatic`, `enable_governance`). Different layer configurations could collide in cache, returning incorrect results. **All layer flags are now part of the cache key.**

**Critical fix — Hybrid Mode Governance Bypass (BUG-12)**:
Hybrid rerank mode (`rerank_mode=hybrid`) took a completely separate code path that bypassed quality gates, PII handling, and governance. `allow_pii=False` with `rerank_mode=hybrid` would return PII content. **Hybrid mode now applies governance post-processing.**

**Other orchestrator fixes**:
- Async endpoint no longer blocks event loop — uses `asyncio.to_thread()` for synchronous orchestrator calls
- `source_origin` and `include_embeddings` filters now properly passed from API to orchestrator
- Lexical and semantic retrieval layers run concurrently via `asyncio.gather` (~30-50% retrieval latency reduction)
- Cache uses true LRU eviction (was labeled LRU but implemented as FIFO)
- Orchestrator singleton cached and reused across requests (was instantiated per request)
- Error responses sanitized — no internal details leaked in 500 responses
- Graph cache invalidation scoped to project (was global on any edge change)

### Why It Matters for DeepSearch

**Score distributions have fundamentally changed.** Any DeepSearch logic that relies on absolute score thresholds (e.g., "results above 0.8 are high-confidence") must be re-calibrated.

### What DeepSearch Needs to Do

- **Re-calibrate score thresholds**: The score compounding fix means scores are now lower and more tightly distributed. A result that previously scored 0.95 (from compounded boosts) may now score 0.70-0.80. Run representative queries and examine the new score distributions.
- **Update pre-flight quality checks**: If DeepSearch pre-flight checks evaluate TraceLab search quality by score ranges, adjust thresholds downward.
- **Leverage the new `score_fusion` metadata**: Results now include a `score_fusion` block showing `base_score`, `type_boost`, `intent_boost`, and `quality_multiplier`. Use these to make more informed relevance decisions.
- **Test hybrid mode**: If using `rerank_mode=hybrid`, verify that governance filtering now correctly applies (previously bypassed).
- **Benefit from latency reduction**: Parallel retrieval layers cut search latency 30-50%. No changes needed, but DeepSearch timeout budgets can be tightened.

---

## 4. Evidence Auto-Linking Upgrade (difflib → Embeddings)

### What Changed

The evidence auto-linking service that matches DeepSearch evidence summaries to TraceLab document chunks has been rewritten from text similarity to semantic similarity.

| Aspect | Previous | New |
|--------|----------|-----|
| Algorithm | `difflib.SequenceMatcher` (string similarity) | Embedding cosine similarity via Qdrant |
| Model | N/A (character-level) | `text-embedding-3-large` (3072d) |
| Matching | Load 750 chunks into memory, O(n*m) comparison | Embed evidence, query Qdrant for nearest neighbors |
| Default threshold | 0.70 | 0.78 |
| Top-K candidates | N/A (all 750) | 3 (`auto_link_top_k`) |
| Fallback | None | difflib available if embedding service unavailable |

**Configuration** (`app/core/config.py`):
- `auto_link_similarity_threshold` = `0.78`
- `auto_link_top_k` = `3`
- `auto_link_fallback_to_difflib` = `True`

**Architecture — Strategy Pattern**:
1. Primary path: `_link_via_embeddings()` — embeds evidence summary, queries Qdrant with project filter, compares cosine similarity against threshold
2. Fallback path: `_link_via_difflib()` — original string matching (activates only if embedding/Qdrant services unavailable and `fallback_to_difflib=True`)

**New error types** added to `AutoLinkErrorType` and `CorrectionErrorType`:
- `EMBEDDING_FAILED` — embedding service error (retryable)
- `QDRANT_ERROR` — vector search error (retryable)

**Telemetry updates**:
- New `linking_method` field: `"embedding"` or `"difflib"`
- Per-match `method` field showing which strategy produced the link
- `runner_up_score` field for threshold calibration analysis

**Public interface unchanged**: `link_evidence(db, mission, project_id, similarity_threshold)` → `EvidenceAutoLinkingResult`

### Why It Matters for DeepSearch

This directly improves DeepSearch ingestion quality. Evidence summaries that use different wording than the original document chunks (paraphrased, summarized, or translated) now match correctly via semantic similarity. Previously, only near-verbatim matches succeeded.

### What DeepSearch Needs to Do

- **Update `similarity_threshold` if passing explicitly**: The default changed from 0.70 to 0.78. If DeepSearch agents pass a custom `similarity_threshold` in the ingest request, review whether to adjust. The new threshold is cosine similarity, not string ratio — they are not equivalent scales.
- **Monitor auto-link success rates**: The embedding approach should produce higher link rates. Track `success_rate` in ingest responses and compare against pre-Sprint-29 baselines.
- **Handle new error types**: If DeepSearch processes the `errors` array from auto-linking results, add handling for `EMBEDDING_FAILED` and `QDRANT_ERROR`. Both are retryable.
- **No API changes**: The ingest endpoint request/response schema is unchanged. The improvement is entirely server-side.

---

## 5. API Endpoint Changes

### Mission Endpoints

#### Changed: Flexible ID Resolution

`GET /api/v1/missions/{mission_id}` and `POST /api/v1/missions/{mission_id}/submit` now accept **both UUID and human-readable mission_id** (e.g., `"B16.1"`).

| Endpoint | Previous | New |
|----------|----------|-----|
| `GET /missions/{mission_id}` | `mission_id: UUID` only | `mission_id: str` (UUID or human-readable) |
| `POST /missions/{mission_id}/submit` | `mission_id: UUID` only | `mission_id: str` (UUID or human-readable) |

Previously, agents had to: `GET /missions?mission_id=B16.1` → extract UUID → `POST /missions/{uuid}/submit`. Now agents can directly use human-readable IDs.

#### New: Create-and-Submit Convenience Endpoint

```
POST /api/v1/missions/create-and-submit
```

**Request**: `MissionCreate` body (same as `POST /missions`)
**Response**: `MissionSubmitResponse` (status 201)
**Purpose**: Creates a mission and immediately queues it for DeepSearch execution in a single call, eliminating the two-step create → submit flow.

#### New: Actionable Error Responses

Mission endpoints now return structured error objects:

```json
{
  "detail": {
    "message": "Mission must be associated with a project before submission",
    "mission_id": "B16.1",
    "uuid": "550e8400-e29b-41d4-a716-446655440000",
    "suggestion": "Use PUT /missions/{id} to set project_id first.",
    "current_status": "draft"
  }
}
```

Schema: `MissionErrorResponse` wrapping `MissionActionableError` with fields:
- `message` (str): Human-readable error
- `mission_id` (Optional[str]): Human-readable ID
- `uuid` (Optional[UUID]): Mission UUID
- `suggestion` (Optional[str]): Actionable fix
- `current_status` (Optional[str]): Current mission status

### PEDR Search Endpoint

#### Changed: Async Execution

`POST /api/v1/pedr/search` now wraps synchronous orchestrator calls in `asyncio.to_thread()`, preventing event loop blocking under concurrent load. No API contract change — this is a performance improvement.

#### Changed: Filter Pass-Through

Two parameters that were previously accepted but silently ignored are now functional:
- `source_origin`: Filters by document origin (`'upload'`, `'synthesized'`, `'imported'`)
- `include_embeddings`: Returns embedding vectors in results for RAG context compression

#### Changed: Hybrid Mode Validation

New schema validator enforces `candidate_pool > top_k` when `rerank_mode="hybrid"`. Requests that previously passed silently now return 400 if `candidate_pool <= top_k`.

#### Changed: PEDRQueryIntent Type

Added `"unknown"` to the intent enum: `"search" | "create" | "update" | "delete" | "execute" | "unknown"`. Cache hit responses previously failed serialization when intent was not determined.

#### Changed: Error Response Sanitization

500 errors now return a generic message: `"Search failed due to an internal error."` instead of leaking internal details. 400 errors still return specific validation messages.

### MCP Tool Alignment

MCP mission tools now include `project_name` in serialized responses and return structured error payloads aligned with the REST API format (`message`, `mission_id`, `uuid`, `suggestion`, `current_status`).

---

## 6. Optimization Recommendations for DeepSearch Agents

### Immediate Wins

1. **Use human-readable IDs everywhere**: Stop doing UUID lookups. `GET /missions/B16.1` and `POST /missions/B16.1/submit` work directly now.

2. **Use create-and-submit for new missions**: Replace the two-step `POST /missions` + `POST /missions/{id}/submit` with `POST /missions/create-and-submit` to cut API calls in half for the common case.

3. **Parse actionable errors**: Error responses now include a `suggestion` field telling you exactly what to do. Build error handling that surfaces these suggestions.

4. **Use `source_origin` filtering**: If querying for specific document types, filter at the API level with `source_origin` instead of post-filtering results client-side.

5. **Request `include_embeddings` when needed**: If performing client-side reranking or caching, request embeddings directly instead of re-embedding result text.

### Search Quality Optimization

6. **Re-calibrate relevance thresholds**: Score distributions are fundamentally different after the compounding fix. Run a calibration pass with representative queries and set new thresholds based on actual score ranges.

7. **Use `score_fusion` metadata for smart filtering**: Instead of a single score threshold, use the decomposed scores (`base_score`, `quality_multiplier`) for more nuanced relevance decisions.

8. **Prefer full PEDR over hybrid for quality-sensitive queries**: Hybrid mode now applies governance, but the full PEDR stack provides deeper quality analysis. Reserve hybrid for latency-sensitive, high-volume queries.

### Integration Health

9. **Match embedding dimensions**: If generating client-side embeddings, ensure `text-embedding-3-large` at 3072 dimensions. Mismatched dimensions will produce garbage similarity scores.

10. **Adjust timeout budgets**: Search latency P95 increased from ~56ms to ~131ms due to larger embeddings, but parallel retrieval offsets this at the orchestrator level. Recommend 500ms timeout for standard queries, 1000ms for graph-enabled queries.

---

## 7. Migration Checklist

Priority-ordered action items for the DeepSearch team:

### Priority 1 — Critical (Breaking if not addressed)

- [ ] **Update client-side embedding model** to `text-embedding-3-large` with `dimensions=3072` (if generating embeddings client-side)
- [ ] **Update any hardcoded dimension references** from 1536 to 3072
- [ ] **Re-calibrate search score thresholds** — scores are lower and tighter after the compounding fix

### Priority 2 — High (Functional impact)

- [ ] **Update `similarity_threshold`** if passing explicitly in ingest requests (default changed from 0.70 to 0.78, now cosine similarity not string ratio)
- [ ] **Handle new error types** `EMBEDDING_FAILED` and `QDRANT_ERROR` in auto-linking result processing
- [ ] **Test hybrid mode behavior** — governance/PII filtering now applies (previously bypassed)
- [ ] **Validate `candidate_pool > top_k`** in hybrid search requests (now enforced, returns 400 if violated)

### Priority 3 — Medium (Optimization)

- [ ] **Switch to human-readable IDs** for mission `GET` and `submit` endpoints
- [ ] **Adopt `POST /missions/create-and-submit`** for one-call mission creation
- [ ] **Parse `MissionActionableError.suggestion`** in error handling code
- [ ] **Use `source_origin` and `include_embeddings`** parameters (now functional)
- [ ] **Update cost tracking** with GPT-5.x pricing (gpt-5.1: $1.25/$10.00 per M tokens; gpt-5.2: $2.00/$16.00 per M tokens)

### Priority 4 — Low (Monitoring)

- [ ] **Monitor auto-link success rates** — expect improvement from semantic matching
- [ ] **Review `score_fusion` metadata** in search results for better relevance decisions
- [ ] **Adjust timeout budgets** if needed (search P95 now ~131ms, up from ~56ms)
- [ ] **Test GPT-5.x synthesis output** for any structural differences in parsed responses

---

## Appendix: File Reference

| Area | Key Files |
|------|-----------|
| LLM config | `app/core/config.py:36-37`, `app/services/cost_monitor.py:13-17` |
| Embedding config | `app/core/config.py:34-35`, `.env.example:36-39` |
| PEDR score fusion | `app/services/pedr/score_utils.py` |
| PEDR orchestrator | `app/services/pedr/search_orchestrator.py`, `app/services/pedr/cache.py` |
| Evidence auto-linking | `app/services/evidence_auto_linking.py`, `app/core/config.py:97-99` |
| Mission API | `app/api/v1/missions.py`, `app/schemas/missions.py` |
| PEDR search API | `app/api/v1/pedr_search.py`, `app/schemas/pedr_search.py` |
| Benchmark results | `docs/embedding-migration-3072-benchmark.md` |

---

*Generated as part of TraceLab Sprint 29 — T29.7 DeepSearch Impact Report*
