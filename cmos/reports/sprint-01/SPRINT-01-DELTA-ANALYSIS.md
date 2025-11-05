# Sprint 01 Delta Analysis - Closing the Gap

**Generated:** 2025-10-31  
**Purpose:** Identify specific actions needed to meet the 3 unmet success criteria

---

## Executive Summary

**Current Status:** 1/4 criteria met  
**Gap to Close:** 3 unmet criteria requiring targeted fixes

---

## 1. Presidio Recall ≥ 0.95 (Priority Entities)

### Current Status
- **Min recall:** 0.9021 (PERSON entity)
- **Gap:** -0.0479 (4.79 percentage points)
- **Target:** ≥0.95

### Current Entity Performance
| Entity | Recall | Met? | Gap |
|--------|--------|------|-----|
| PERSON | 0.9021 | ❌ | -0.0479 |
| EMAIL_ADDRESS | 0.9412 | ❌ | -0.0088 |
| PHONE_NUMBER | 0.9231 | ❌ | -0.0269 |
| PARTICIPANT_ID | 0.9167 | ❌ | -0.0333 |
| PROJECT_ID | 0.9167 | ❌ | -0.0333 |

### Root Cause Analysis
From `presidio_tuned_results.json`:
- **PERSON**: 14 annotated, 13 true positives, **1 false negative** → Missing 1 person name
- **EMAIL_ADDRESS**: 17 annotated, 16 true positives, **1 false negative** → Missing 1 email
- **PHONE_NUMBER**: 13 annotated, 12 true positives, **1 false negative** → Missing 1 phone
- **PARTICIPANT_ID**: 12 annotated, 11 true positives, **1 false negative** → Missing 1 participant ID
- **PROJECT_ID**: 12 annotated, 11 true positives, **1 false negative** → Missing 1 project ID

### Action Items to Close Gap

#### Option A: Pattern Recognizer Tuning (Recommended)
1. **Lower entity score thresholds** in `app/services/presidio_redaction.py`:
   - Default Presidio threshold is typically 0.3-0.5
   - Adjust AnalyzerEngine confidence levels for PERSON entity
   - Add more pattern variations for PARTICIPANT_ID and PROJECT_ID

2. **Improve PERSON recognition**:
   - Analyze the false negative to understand pattern (e.g., unusual name format, context-dependent)
   - Consider adding a custom PatternRecognizer with broader regex patterns
   - Adjust NER model confidence threshold

3. **Add deny-list patterns**:
   - Review corpus to identify common false negatives
   - Add patterns to `config/redaction_deny_list.json` if applicable

#### Option B: Corpus Expansion
- Generate larger corpus to reduce variance (current: 27 samples)
- Test with 100+ samples for more stable metrics

#### Option C: Custom Entity Recognizer
- Implement context-aware PERSON recognizer
- Use spaCy NER model fine-tuning if needed

**Estimated Effort:** 2-4 hours  
**Recommended Approach:** Option A (tune existing recognizers)

---

## 2. Five Priority Formats Ingested End-to-End

### Current Status
- **Artifact Missing:** `ingestion_format_coverage.json` does not exist
- **Code Status:** Coverage report generator is implemented and called in `DocumentIngestionService`
- **Root Cause:** No documents have been uploaded/processed via the API

### Action Items

1. **Upload test documents** for all 5 formats:
   ```bash
   # PDF
   curl -X POST "http://localhost:8000/api/v1/documents/upload?project_id=<UUID>" \
     -F "file=@test_doc.pdf" -F "source_type=report"
   
   # DOCX
   curl -X POST "http://localhost:8000/api/v1/documents/upload?project_id=<UUID>" \
     -F "file=@test_doc.docx" -F "source_type=report"
   
   # PPTX
   curl -X POST "http://localhost:8000/api/v1/documents/upload?project_id=<UUID>" \
     -F "file=@test_doc.pptx" -F "source_type=report"
   
   # CSV
   curl -X POST "http://localhost:8000/api/v1/documents/upload?project_id=<UUID>" \
     -F "file=@test_doc.csv" -F "source_type=survey"
   
   # XLSX
   curl -X POST "http://localhost:8000/api/v1/documents/upload?project_id=<UUID>" \
     -F "file=@test_doc.xlsx" -F "source_type=survey"
   ```

2. **Process each uploaded document**:
   ```bash
   curl -X POST "http://localhost:8000/api/v1/documents/<DOCUMENT_ID>/process"
   ```

3. **Verify coverage report generation**:
   - Check `cmos/reports/sprint-01/ingestion_format_coverage.json` exists
   - Verify all 5 formats show `chunked > 0`

### Test Data Sources
- Use synthetic corpus from `data/corpus/` (generated via B1.2)
- Create minimal test files per format
- Reuse corpus generator output

**Estimated Effort:** 30-60 minutes  
**Risk:** Low (code is implemented, just needs execution)

---

## 3. Qdrant Query Latency <10ms p99

### Current Status
- **Top-k=5:** 6.8ms ✅ (meets target)
- **Top-k=10:** 9.5ms ✅ (meets target)
- **Top-k=20:** 14.3ms ❌ (fails target, +4.3ms)
- **Current hnsw_ef:** 128 (for top_k=5,10), 160 (for top_k=20)

### Root Cause
- Query evaluation uses `max(query_latency)` as proxy for p99
- Top-k=20 query uses `hnsw_ef=160`, increasing search scope
- Target metric requires ALL query scenarios <10ms

### Action Items

#### Option A: Reduce hnsw_ef for top_k=20 (Quick Fix)
1. **Modify query script** that generates `qdrant_performance.json`:
   - Change `hnsw_ef` from 160 → 128 or lower for top_k=20
   - Re-run performance test

2. **Update search_chunks method** in `app/services/qdrant_service.py`:
   - Default `hnsw_ef=128` for all queries
   - Optionally make it adaptive based on top_k

#### Option B: Optimize HNSW Index Configuration
1. **Review collection HNSW settings** in `app/services/qdrant_service.py`:
   - Current: `m=16`, `ef_construct=100`
   - Consider: Increase `m` to 24-32 (trades memory for faster queries)
   - Keep `on_disk=False` for HNSW graph (already correct)

2. **Verify scalar quantization**:
   - Current: `scalar_int8` quantization enabled
   - Ensure quantization is applied (may require collection recreation)

#### Option C: Query Strategy Optimization
1. **Implement rescoring** (per TR-04 research):
   - Use oversampling + rescoring to reduce `hnsw_ef` while maintaining accuracy
   - Oversample 2x top_k, then rescore with full-precision vectors

**Estimated Effort:** 1-2 hours  
**Recommended Approach:** Option A (reduce ef for top_k=20), then Option C if needed

---

## Implementation Priority

1. **Format Coverage (2)** - Fastest win (30-60 min)
2. **Qdrant Latency (3)** - Moderate effort (1-2 hours)
3. **Presidio Recall (1)** - Requires tuning/testing (2-4 hours)

**Total Estimated Time:** 3.5-6.5 hours

---

## Verification Checklist

After implementing fixes:

- [ ] Run `python scripts/evaluate_presidio.py` and verify recall ≥ 0.95
- [ ] Upload/process documents for all 5 formats
- [ ] Verify `ingestion_format_coverage.json` shows all formats with `chunked > 0`
- [ ] Re-run Qdrant performance test with updated `hnsw_ef` settings
- [ ] Verify `qdrant_performance.json` shows max latency <10ms
- [ ] Run `python scripts/evaluate_sprint.py --sprint 1` to confirm all criteria met
