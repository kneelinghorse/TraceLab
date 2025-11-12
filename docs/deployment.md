# Deployment Runbook

This guide extends the environment provisioning workflow captured in `docs/implementation_guide.md` (see **Step 9: Qdrant Vector Database Setup**) with the operational checks required for Sprint 07. Use it whenever a new environment is spun up or restored to ensure the vector database stays aligned with TraceLab's expectations.

## Qdrant Initialization Flow

1. **Authenticate** using the admin credentials described in `docs/authentication.md`:
   ```bash
   curl -X POST "$API_URL/api/v1/auth/login" \
     -H "Content-Type: application/json" \
     -d '{"username": "'$AUTH_USERNAME'", "password": "'$AUTH_PASSWORD'"}'
   ```
   Capture the `access_token` from the response for the remaining calls.

2. **Initialize the collection** (idempotent). Run after every fresh deployment or when telemetry reports missing collections:
   ```bash
   curl -X POST "$API_URL/api/v1/admin/init-qdrant" \
     -H "Authorization: Bearer $ACCESS_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"write_optimized": false}'
   ```
   - Use `write_optimized=true` only before large backfills (bulk ingestion); remember to re-enable indexing via `QdrantService.enable_indexing_and_quantization()` once ingestion finishes.
   - Successful calls return `status=initialized`, `collection=research_chunks`, and echo the write-mode that was applied.

3. **Verify health and schema** with the dedicated endpoint:
   ```bash
   curl -X GET "$API_URL/api/v1/admin/health" \
     -H "Authorization: Bearer $ACCESS_TOKEN"
   ```
   The response confirms:
   - Qdrant connectivity (`status=healthy`).
   - Collection presence (`collection_exists=true`).
   - Actual vs. expected vector dimensions (should be 1536) and distance metric (COSINE) so deviations are easy to spot during ops reviews.

4. **Document the run** by appending the command outputs to your deployment journal and ensuring `python cmos/scripts/validate_parity.py --check` still passes. If problems persist, follow the remediation checklist in `docs/implementation_guide.md` (Qdrant section) before escalating.

## Operational Notes

- These endpoints are protected by bearer authentication; rotate credentials per `docs/auth_and_cors_guidance.md` after handoffs.
- Telemetry for Qdrant health should be recorded in `telemetry/events/database-health.jsonl` alongside existing DB checks so CMOS agents can trace collection drift.
- Never create or drop collections manually through the Qdrant UI when working on TraceLab—use these endpoints so the same configuration applies across all environments.
