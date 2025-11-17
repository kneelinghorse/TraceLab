# Quality-Aware Search (PEDR Phase 1)

Sprint 10 introduces a PEDR-backed quality ranking layer that boosts complete, validated missions in hybrid search results. The implementation lives in `app/services/pedr/` and integrates directly with `HybridSearchService`.

## Scoring Model

Quality scoring is computed per mission and then applied to every chunk associated with that mission:

1. **Base score** – count of passing gates across the five Mission Protocol checkpoints (`research_statement`, `evidence_links`, `synthesis_quality`, `traceability`, `contradictions_resolved`) divided by five.
2. **Status boost** – applied according to mission status:
   - `complete`: +0.20
   - `review`: +0.10
   - `in_progress`: +0.05
   - `draft`: +0.00
3. **Validation boost** – +0.05 when every gate reports `validated=True`.
4. **Final multiplier** – `base_score * (1 + total_boost)`, clamped between `0.10` and `1.50`.

The multiplier is applied to each chunk’s `combined_score`, ensuring complete missions rank roughly 2× higher than drafts with partial gates.

## Governance Filters

`HybridSearchService.search()` and `/api/v1/search` now honor three new parameters surfaced via `RagQuery`:

- `min_quality_gates` (0–5): minimum number of passing gates required.
- `status`: optional list of allowed mission statuses (e.g., `["complete", "review"]`).
- `allow_pii`: when `False`, drops any mission flagged for PII handling (detected from mission governance metadata or tags).

Filters are normalized into the cache key (`CacheManager.rag_query_key`) so cached answers respect the same governance constraints.

## Response Metadata

Every retrieved chunk now includes additional metadata:

| Field | Description |
|-------|-------------|
| `quality_score` | Final multiplier applied to the chunk. |
| `quality_base_score` | Base ratio from quality gates. |
| `quality_boost` | Combined boost from status + validation. |
| `quality_status` | Mission status used for ranking. |
| `quality_gates_passed` / `quality_gates_total` | Gate counts powering the base score. |
| `quality_validated` | Indicates whether every gate is validated. |
| `quality_mission_id` | Mission identifier used for scoring. |
| `quality_pii_flagged` | Flag showing whether the mission was marked as PII-handling. |

These fields propagate through the FastAPI response (see `app/schemas/retrieval.py`) so UI layers can present ranking rationale alongside each result.

## Tests & Guardrails

- `tests/test_quality_aware_search.py` covers ten scenarios spanning scoring, boosts, filters, and metadata loader behavior.
- `tests/test_hybrid_search.py` now injects a quality service stub to keep the hybrid tests deterministic.
- When updating quality logic, run `pytest tests/test_quality_aware_search.py` to ensure scoring regressions are caught.

Refer back to this document whenever adjusting PEDR weighting or adding new governance filters to keep the service, API, and docs aligned.
