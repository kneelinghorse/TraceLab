# Lightweight Redaction Guardrail

## Overview

TraceLab no longer ships Microsoft Presidio or spaCy dependencies. The
`PresidioRedactionService` name is preserved for compatibility, but it now uses
simple regexes plus optional deny lists to hide obvious identifiers. Document
ingestion **skips redaction entirely**—raw text is parsed and chunked directly—
and only the `/api/v1/redaction` endpoint relies on the stubbed service.

## Key Changes

- **Dependency removal**: `presidio-*` packages are gone from `requirements.txt`.
- **Passthrough ingestion**: `DocumentIngestionService` records a `"redacted"`
  stage for audit history but no longer modifies content.
- **Regex recognizers**: Participant IDs, project IDs, emails, and phones are
  spotted with compiled regexes instead of Presidio analyzers.
- **Deterministic pseudonyms**: Matches are replaced with
  `<ENTITY>-PSEUDO-XXXX` tokens when `use_pseudonymization=True`.
- **No regression tooling**: `scripts/evaluate_presidio.py` and
  `scripts/run_regression_evaluation.py` now emit retirement notices.

## Usage

```python
from app.services.presidio_redaction import PresidioRedactionService

service = PresidioRedactionService()
result = service.redact_document(
    text="Participant PID-2024-1234 reached out via john@example.com",
    document_id="doc-001",
    metadata={"doc_type": "transcript"},
)

print(result["redacted_text"])
print(result["entities"])
print(result["audit_trail"])
```

API access is unchanged:

```bash
curl -X POST http://localhost:8000/api/v1/redaction/redact \
  -H "Content-Type: application/json" \
  -d '{"text":"PID-2024-1234", "use_pseudonymization": true}'
```

## Guardrail Checklist

- [x] Ingestion pipeline skips Presidio redaction and records `"redaction_enabled": false`.
- [x] `pytest tests/test_presidio_redaction.py::test_redact_document_uses_pseudonymization_and_audit`
      verifies audit + pseudonym tokens.
- [x] `/api/v1/redaction/redact` continues to respond successfully in tests.

## Files

- `app/services/presidio_redaction.py` – Regex-based service stub.
- `app/services/document_ingestion.py` – Records redaction as a skipped stage.
- `app/api/v1/redaction.py` – FastAPI routes.
- `scripts/evaluate_presidio.py`, `scripts/run_regression_evaluation.py` – Shims that now exit with deprecation notices.
