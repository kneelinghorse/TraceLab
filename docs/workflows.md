# End-to-End Workflow Reference

TraceLab's Sprint 07 workflow validation proves both the browser workspace and the automation-friendly CLI can shepherd a document from upload through RAG answers with identical guardrails. Use this guide when running the mission-protocol validation loop or onboarding a new team member who needs a single-page view of the workflow.

## Prerequisites
- Core services running: PostgreSQL + Qdrant (`docker-compose up -d`), FastAPI (`uvicorn app.main:app --reload`), and the Next.js Mission Protocol frontend (`cd frontend && npm run dev`).
- Environment configured with valid `OPENAI_API_KEY`, `QDRANT_URL`, and auth credentials from `AUTH_USERNAME` / `AUTH_PASSWORD`.
- Mission Protocol SQLite mirrors synced via `python cmos/scripts/migrate_cmos_memory.py --source cmos --target cmos --sync-db` and parity verified with `python cmos/scripts/validate_parity.py --check`.
- (Optional) When running Playwright automation locally, export `NEXT_PUBLIC_E2E_AUTH_TOKEN` to bypass the login panel inside controlled test runs.

## Browser Workflow
1. **Authenticate** – Navigate to `/missions` and sign in with the configured credentials. Authenticated sessions surface the sticky mission header plus nav links to Documents, Projects, Missions, and Search.
2. **Create a project** – Use the Projects page to add a project (name + description). The form issues `POST /api/v1/projects`, which the FastAPI service persists in PostgreSQL.
3. **Upload a document** – Switch to Documents, click *Upload*, select a PDF/Markdown/Docx source, and toggle `Process document after upload`. The UI calls `POST /api/v1/documents/upload` followed by `POST /api/v1/documents/{id}/process`.
4. **Monitor processing** – The processing drawer replays `document_processing_statuses` rows so you can confirm `extracted → chunked → embedded`. Any failures bubble up immediately; retry from the action menu.
5. **Validate mission data** – Return to Missions. The backlog column cards reflect completion %, status, and gate count. Editing a mission opens the Mission Protocol form plus live `QualityGatePanel`, which fetches `/quality/missions/{id}/quality` every 15s.
6. **Search + capture evidence** – Hit `/search`, run a semantic query, and review highlighted chunks. Use *Quick Add* on a result card to associate a chunk with the active mission; this toggles the traceability gate state in real time.
7. **Run RAG + review citations** – Use the *Ask TraceLab* composer on the right rail to run a RAG query. Responses cite document + chunk IDs and persist a transcript in the lower timeline for auditing.
8. **Export + share** – From the mission detail page, download Markdown/PDF/DOCX exports via `/missions/{id}/export`. The export includes current gate states, evidence, and RAG answers for review.

## CLI Workflow
1. **Authenticate**
   ```bash
   tracelab auth login --username $AUTH_USERNAME --password $AUTH_PASSWORD
   tracelab auth status
   ```
2. **Create or fetch a project**
   ```bash
   PROJECT_ID=$(tracelab projects create --name "Research" --description "Sprint 07 validation" --json | jq -r '.data.id')
   # or reuse an existing project via tracelab projects list
   ```
3. **Upload + process document**
   ```bash
   tracelab documents upload "$PROJECT_ID" ./docs/sample.md --process --wait --json > /tmp/doc.json
   DOCUMENT_ID=$(jq -r '.data.id' /tmp/doc.json)
   ```
   `--process --wait` blocks until the ingestion job populates `DocumentChunk` rows and embeds vectors via Qdrant.
4. **Check processing + parity**
   ```bash
   tracelab documents status "$DOCUMENT_ID"
   python scripts/verify_ingestion_parity.py "$DOCUMENT_ID"
   ```
5. **Search & run RAG**
   ```bash
   tracelab search semantic "$PROJECT_ID" "mission readiness" --top-k 5 --json
   tracelab rag query "$PROJECT_ID" "Summarize the backlog blockers" --top-k 4 --json
   ```
   Capture the highest scoring chunks for each answer.
6. **Attach evidence + export**
   ```bash
   MISSION_ID=$(tracelab missions create "$PROJECT_ID" --title "Sprint 07 E2E" --json | jq -r '.data.id')
   tracelab missions add-evidence "$MISSION_ID" "$CHUNK_ID"
   tracelab missions export "$MISSION_ID" --format md --output sprint-07-validation.md
   ```

## Automated Validation Coverage (B7.7)
The following suites confirm the workflow stays green. Rerun them before promoting a new build:
- `pytest tests/test_document_ingestion.py tests/test_document_embedding_integration.py` – ingestion stages, chunk counters, and embeddings audit events.
- `pytest tests/test_retrieval_service.py tests/test_rag_service.py tests/integration/test_rag_pipeline.py` – semantic search + cached RAG run with quality scoring.
- `pytest tests/integration/test_ingestion_flow.py` – CLI upload script driving FastAPI + parity report generation.
- `cd frontend && NEXT_PUBLIC_E2E_AUTH_TOKEN=test-playwright npx playwright test tests/e2e/mission-protocol.spec.ts --project=chromium` – Mission Protocol UI backlog + mission detail flows with mocked APIs.

## Troubleshooting Notes
- **Auth failing in tests** – Provide `NEXT_PUBLIC_E2E_AUTH_TOKEN` (any string) before running Playwright to auto-bootstrap an authenticated context.
- **Embedding skips** – Ensure `OPENAI_API_KEY` and a secure `QDRANT_URL` are set; see `docs/document-processing.md`.
- **Search returns empty results** – Confirm the document’s project matches the query filters and that `chunks_embedded` is non-zero via the parity report.
- **Mission gates stuck** – Click *Refresh* on the backlog grid, then re-open the detail page to force the SWR hooks to refetch `/quality/missions/{id}/quality`.
