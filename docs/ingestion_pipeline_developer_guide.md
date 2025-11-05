# Document Ingestion Pipeline Guide

## Overview

The Sprint B1.4 ingestion workflow accepts the five prioritized UX research formats—PDF, DOCX, PPTX, CSV, and XLSX—and orchestrates the following stages:

1. **Upload** – Files are accepted through `POST /api/v1/documents/upload` and stored under `data/uploads/`. A document record is created immediately and an `uploaded` processing event is persisted.
2. **Extraction** – `DocumentIngestionService` detects the format and routes it to the appropriate parser (pdfminer.six, python-docx, python-pptx, pandas/openpyxl). Successful runs emit an `extracted` event with token counts.
3. **Redaction** – The Presidio service (re-used from B1.3) pseudonymizes detected entities before any persistence. The document body stored in the database is always redacted, and an audit event is recorded under the `redacted` stage.
4. **Chunking** – Redacted text is split into 500–1000 token chunks (750 target, 50 token overlap) with positional metadata. Persistence stores `DocumentChunk` rows and links `prev/next` references. Completion is tracked with a `chunked` event.
5. **Coverage Reporting** – Every successful run refreshes `cmos/reports/sprint-01/ingestion_format_coverage.json`, summarizing success, failure, and progress metrics per format.

Processing state is persisted in `document_processing_statuses` with the following schema:

| column          | type    | meaning                                      |
|-----------------|---------|----------------------------------------------|
| `stage`         | text    | `uploaded`, `extracted`, `redacted`, `chunked`, `pipeline` |
| `status`        | text    | `in_progress`, `succeeded`, `failed`         |
| `message`       | text    | Optional human-readable context              |
| `details`       | JSON    | Structured metadata (lengths, counts, etc.)  |
| `created_at`    | datetime | Event timestamp (UTC)                       |

Use `GET /api/v1/documents/{id}` to retrieve the status history; the response now includes `processing_events` alongside `chunks` and `tags`.

## API Usage

### Uploading a Document

```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload?project_id=<PROJECT_UUID>" \\
  -F "file=@/path/to/interview.pdf" \\
  -F "source_type=interview"
```

**Success Response (`HTTP 200`)**

```json
{
  "id": "c5c5f5ac-1f7d-4a2c-b33e-4a5ac55f6fc2",
  "project_id": "<PROJECT_UUID>",
  "name": "interview.pdf",
  "file_type": "report",
  "processed": false,
  "chunked": false,
  "processing_events": [
    {
      "stage": "uploaded",
      "status": "succeeded",
      "details": {
        "file_name": "interview.pdf",
        "file_size_bytes": 482134
      },
      "created_at": "2025-10-31T21:10:12.513Z"
    }
  ]
}
```

### Processing a Document

```bash
curl -X POST \
  "http://localhost:8000/api/v1/documents/c5c5f5ac-1f7d-4a2c-b33e-4a5ac55f6fc2/process"
```

**Success Response (`HTTP 200`)**

```json
{
  "document_id": "c5c5f5ac-1f7d-4a2c-b33e-4a5ac55f6fc2",
  "status": "completed",
  "stages": {
    "extracted": {
      "status": "success",
      "text_length": 4128
    },
    "redacted": {
      "status": "success",
      "entities_detected": 7,
      "redacted_text_length": 4159
    },
    "chunked": {
      "status": "success",
      "chunk_count": 2
    },
    "persisted": {
      "status": "success",
      "chunks_created": 2
    }
  }
}
```

When failures occur (for example, parsing errors), the service records a `failed` event with diagnostic details and flags the document’s `validation_status` as `flagged` for manual review.

## Developer Notes

- **Parsers**
  - PDFs: `pdfminer.six`
  - DOCX: `python-docx`
  - PPTX: `python-pptx`
  - CSV/XLSX: `pandas` with `openpyxl`
- **Redaction** – Presidio is lazily instantiated via `app.api.v1.redaction.get_redaction_service()`. Tests inject a stub using the same hook.
- **Chunking** – Defined in `app/services/chunking.py`. Chunks include overlap to preserve context and store start/end character offsets plus estimated token counts.
- **Coverage Metrics** – Regenerated automatically on successful processing. Inspect `cmos/reports/sprint-01/ingestion_format_coverage.json` for up-to-date counts and rates per format.
- **Testing** – `tests/test_document_ingestion.py` provides end-to-end coverage for all formats with dependency stubs, ensuring deterministic results.

## Quick Troubleshooting

| Symptom | Likely Cause | Resolution |
|---------|--------------|------------|
| `Unsupported file format` error | Missing extension or unsupported type | Ensure uploads use `.pdf`, `.docx`, `.pptx`, `.csv`, `.xlsx` |
| Processing fails with `pdfminer.six is not installed` | Dependency missing | Install project requirements (`pip install -r requirements.txt`) |
| Coverage file not updating | Processing halted before completion | Check `document_processing_statuses` for failed stages, rerun after resolving root cause |
| API tests failing with `AsyncClient.__init__` kwargs | httpx ≥0.26 change | Use `ASGITransport(app=app)` when creating in-tests clients |

This pipeline is the foundation for B1.5 (embedding & Qdrant). Downstream services can rely on sanitized, chunked content with full audit traceability per document.
