# Synthetic UX Research Corpus

This directory contains the synthetic UX research corpus generated for Presidio evaluation.

## Overview

The corpus is programmatically generated using Faker to create realistic but entirely synthetic PII. This ensures privacy compliance while providing representative test data for PII detection evaluation.

## Directory Structure

```
data/corpus/
├── transcripts/          # Interview transcripts (TXT, DOCX)
├── surveys/              # Survey responses (CSV)
├── personas/             # User personas (PDF, DOCX)
├── test_notes/           # Usability test notes (TXT)
├── briefs/               # Research briefs (Markdown)
├── annotations/          # Ground-truth PII annotations (JSON + source text)
└── corpus_metadata.json  # Corpus generation metadata & statistics
```

## Generation

To generate the corpus:

```bash
python scripts/generate_corpus.py
```

Options:
- `--output-dir DIR`: Specify output directory (default: `data/corpus`)
- `--seed SEED`: Set random seed for reproducibility (default: 42)
- `--transcript-txt N`: Number of TXT transcripts (default: 200)
- `--transcript-docx N`: Number of DOCX transcripts (default: 200)
- `--survey-responses N`: Number of survey rows in the CSV artifact (default: 300)
- `--persona-pdf N`: Number of PDF personas (default: 75)
- `--persona-docx N`: Number of DOCX personas (default: 75)
- `--test-notes N`: Number of test notes (default: 150)
- `--research-briefs N`: Number of Markdown research briefs (default: 100)

## Annotation Format

Each document has a corresponding annotation JSON file in `annotations/` with the format:

```json
[
  {
    "start": 45,
    "end": 56,
    "entity_type": "PERSON",
    "value": "John Doe"
  },
  {
    "start": 78,
    "end": 102,
    "entity_type": "EMAIL_ADDRESS",
    "value": "john.doe@example.com"
  }
]
```

## Evaluation

After generating the corpus, evaluate Presidio performance:

```bash
python scripts/evaluate_presidio.py
```

Options:
- `--corpus-dir DIR`: Corpus directory (default: `data/corpus`)
- `--output FILE`: Output report path (default: `cmos/reports/sprint-01/presidio_corpus_baseline.json`)

The evaluator leverages the source text snapshots persisted alongside annotations to ensure offsets remain accurate across TXT, CSV, DOCX, PDF, and Markdown exemplars.

## Packaging for Secure Storage

Package the corpus into a signed archive with manifest metadata:

```bash
python scripts/package_corpus.py \
  --corpus-dir data/corpus \
  --output-dir artifacts/corpus_packages
```

This creates a `.tar.gz` (or `.zip`) archive, `*_manifest.json`, and optionally copies the latest baseline report for integrity tracking.

To stage the package for upload to a secure bucket or vault:

```bash
python scripts/upload_corpus.py \
  --corpus-dir data/corpus \
  --output-dir artifacts/corpus_packages \
  --destination /secure/presidio/upload
```

The upload helper copies the archive, manifest, and baseline report into the destination directory so that platform-specific tooling (AWS CLI, Azure CLI, etc.) can promote the artifacts to managed storage following privacy-by-design policies.

## Cloud Storage (Future)

For production use, the corpus should be stored in a secure cloud bucket (Azure Blob Storage, AWS S3, or GCS) with:
- Encryption at rest and in transit
- Strict IAM/RBAC access control
- Versioned storage structure

Manual upload instructions will be documented here when cloud infrastructure is provisioned.

## Notes

- All PII is synthetic and generated via Faker
- Corpus files are excluded from version control (see `.gitignore`)
- Regenerate corpus with the same seed for reproducibility
- Ground-truth annotations enable precision/recall evaluation
