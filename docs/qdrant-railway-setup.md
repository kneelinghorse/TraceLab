# Qdrant Deployment Guide (Cloud + Local)

TraceLab now standardizes on **Qdrant Cloud** for production while keeping Docker/Qdrant-on-Railway workflows for local development or legacy environments. This document captures both paths so operators know exactly which knobs to turn.

---

## Production: Qdrant Cloud Cluster

1. **Provision the cluster**
   - Create a Qdrant Cloud project (we use `us-east4`).
   - Copy the HTTPS endpoint, e.g. `https://7fee7d1f-3b87-4d27-8414-14edd2c84acb.us-east4-0.gcp.cloud.qdrant.io`.
   - Generate an API key with `Collections: read/write` permissions.

2. **Configure Railway application service**

   ```bash
   QDRANT_URL=https://7fee7d1f-3b87-4d27-8414-14edd2c84acb.us-east4-0.gcp.cloud.qdrant.io
   QDRANT_API_KEY=<cloud_api_key>
   QDRANT_COLLECTION_NAME=research_chunks
   QDRANT_PREFER_GRPC=False        # default in config.py, keep REST for Cloud
   QDRANT_TIMEOUT_SECONDS=10.0      # bump if ingesting over slow links
   ```

   > **Reminder:** The FastAPI service owns initialization via `POST /api/v1/admin/init-qdrant`. Always log in, hit the init endpoint, and then `GET /api/v1/admin/health` after every deployment to confirm collection status and payload indexes.

3. **Bulk ingest toggle**
   - Before large backfills, call `POST /api/v1/admin/init-qdrant` with `{"write_optimized": true}`.
   - After ingestion, call the same endpoint with `{"write_optimized": false}` (or run `QdrantService.enable_indexing_and_quantization()` if you need the additional tuning pass).

4. **Verification checklist**
   ```bash
   # Direct Cloud ping (bypasses FastAPI)
   curl -i "$QDRANT_URL/collections" -H "api-key: $QDRANT_API_KEY"

   # Application-level health
   curl -H "Authorization: Bearer $ACCESS_TOKEN" \
     https://api.namozine.com/api/v1/admin/health
   ```
   Expect `status=healthy`, `collection_exists=true`, and every entry in `payload_indexes` reporting `present=true`.

---

## Local Development (Docker Compose)

Use these entries in `.env` when running the local stack:

```bash
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION_NAME=research_chunks
```

Start the service with:

```bash
docker run -p 6333:6333 -p 6334:6334 \
  -v "$(pwd)/qdrant_storage:/qdrant/storage:z" \
  qdrant/qdrant
```

The `npm run dev:all` helper already spins up this container via `docker-compose.dev.yml`.

---

## Legacy (Railway-Hosted Qdrant) – Optional

We no longer use the Railway Qdrant template for production, but if you need a quick disposable vector store inside Railway:

1. Create a Qdrant service, add a volume at `/qdrant/storage`, and set:

   ```bash
   QDRANT__SERVICE__API_KEY=your_secure_key
   QDRANT__STORAGE__PATH=/qdrant/storage
   QDRANT__LOG_LEVEL=INFO
   ```

2. Point the FastAPI service at the generated HTTPS endpoint (the pattern used pre-Sprint 7).

> Treat this mode as best-effort. Cloud is the supported path for parity with production.

---

## Troubleshooting Cheatsheet

- **`{"detail":"Qdrant health check failed: timed out"}`**  
  - Verify `QDRANT_URL` is reachable with `curl`, confirm API key, and ensure `QDRANT_PREFER_GRPC=False` for cloud deployments.

- **`Unexpected Response: 403 (Forbidden)` from qdrant-client**  
  - API key is missing or incorrect; rotate the key in Qdrant Cloud and update Railway.

- **Payload indexes missing**  
  - Re-run `POST /api/v1/admin/init-qdrant` (it is idempotent and recreates the expected indexes).

- **Bulk ingest stuck in write mode**  
  - Reissue the init endpoint with `{"write_optimized": false}` and monitor `/api/v1/admin/health`.

Document every fix in `telemetry/events/database-health.jsonl` and rerun `python cmos/scripts/validate_parity.py --check` whenever you touch the vector infrastructure.
