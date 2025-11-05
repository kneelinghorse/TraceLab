# Presidio Redaction Service

## Overview

The Presidio Redaction Service integrates Microsoft Presidio with custom recognizers for UX research domain-specific entities, implements pseudonymization using Faker, and provides a callable interface for document redaction.

## Features

- **spaCy Model**: Uses `en_core_web_lg` for improved accuracy
- **Custom Recognizers**:
  - `PARTICIPANT_ID`: Recognizes patterns like `PID-2024-1234`, `PARTICIPANT-ABC-1234`, `P-2024-0001`
  - `PROJECT_ID`: Recognizes patterns like `PROJ-ALPHA-1234`, `PROJECT-BETA-9999`
- **Deny Lists**: Configurable at `config/redaction_deny_list.json` to suppress known false positives for participant and project identifiers
- **Pseudonymization**: Uses Faker to generate realistic but fake replacements for detected entities
- **FastAPI Integration**: RESTful API endpoint for document redaction

## Usage

### As a Python Module

```python
from app.services.presidio_redaction import PresidioRedactionService

# Initialize service
service = PresidioRedactionService(spacy_model="en_core_web_lg", locale="en_US")

# Redact a document
text = "Participant PID-2024-1234 named John Smith can be reached at john@example.com."
result = service.redact_document(text, document_id="doc-001")

print(result["redacted_text"])  # Redacted text with pseudonymized entities
print(result["entities"])  # List of detected entities
print(result["audit_trail"])  # Summary of redaction operations
```

### Via FastAPI Endpoint

```bash
curl -X POST http://localhost:8000/api/v1/redaction/redact \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Participant PID-2024-1234 named John Smith can be reached at john@example.com.",
    "document_id": "doc-001",
    "use_pseudonymization": true
  }'
```

### Regression Evaluation

Run the regression evaluation script to compare tuned configuration against baseline:

```bash
python scripts/run_regression_evaluation.py \
  --corpus-dir data/corpus \
  --baseline-report cmos/reports/sprint-01/presidio_corpus_baseline.json \
  --output cmos/reports/sprint-01/presidio_tuned_results.json
```

**Note**: This requires:
1. Corpus generation (from B1.2): `python scripts/generate_corpus.py`
2. Baseline evaluation (from B1.2): `python scripts/evaluate_presidio.py`
3. Regenerated corpus to include new participant/project identifiers introduced in B1.3

## Configuration

The service can be configured with:
- `spacy_model`: spaCy model name (default: `en_core_web_lg`)
- `locale`: Faker locale for pseudonymization (default: `en_US`)

## Pseudonymization Operators

The service uses Faker to generate replacements:
- `PERSON` → Fake name
- `EMAIL_ADDRESS` → Fake email
- `PHONE_NUMBER` → Fake phone number
- `LOCATION` → Fake city and state
- `DATE_TIME` → Fake date
- `PARTICIPANT_ID` → Fake participant ID (PID-YYYY-NNNN format)
- `PROJECT_ID` → Fake project ID (PROJ-WORD-NNNN format)
- `<REDACTED>` fallback applied automatically when pseudonymization is disabled

## Architecture

```
PresidioRedactionService
├── AnalyzerEngine (en_core_web_lg)
│   ├── Built-in Presidio recognizers
│   ├── ParticipantIDRecognizer (custom)
│   └── ProjectIDRecognizer (custom)
└── AnonymizerEngine
    └── Pseudonymization operators (Faker-based)
```

## Files

- `app/services/presidio_redaction.py`: Core service implementation
- `config/redaction_deny_list.json`: Domain-specific deny-list configuration for Presidio recognizers
- `app/api/v1/redaction.py`: FastAPI routes
- `scripts/run_regression_evaluation.py`: Regression evaluation script
