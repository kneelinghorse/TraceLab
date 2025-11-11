# Mission Report Export Workflow

Generate human-readable mission summaries directly from the Mission Protocol data model. The export
pipeline renders a canonical Markdown template, then converts it to PDF or DOCX when needed so every
format shares identical structure, citations, and quality gate coverage.

## Available Formats

| Format | Mime Type | Notes |
| --- | --- | --- |
| `md` | `text/markdown` | Canonical template stored at `app/templates/reports/mission.md.j2`. |
| `pdf` | `application/pdf` | Requires `reportlab`. Styled headings, bullet points, and paragraphs generated from the Markdown blocks. |
| `docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | Requires `python-docx`. Useful for editors that prefer Word documents. |
| `yaml` | `application/json` payload containing raw Mission Protocol YAML (legacy behavior). |

If the environment is missing `python-docx` or `reportlab`, the service raises a descriptive error so
agents can install the dependency before retrying the export.

## Backend Endpoint

```
GET /api/v1/missions/{mission_uuid}/export?format=md|pdf|docx|yaml
```

- When `format=yaml` (default) the endpoint returns a JSON payload like `{"mission_id": ..., "yaml_text": ...}`.
- For `md|pdf|docx` the response is a file download with a `Content-Disposition` header that includes the
  mission-specific filename.
- The endpoint accepts bearer authentication identical to other Mission Protocol routes.

## CLI Usage

```
# Markdown to stdout
tracelab missions export <mission_uuid> --format md

# PDF/DOCX to file (auto filename from headers)
tracelab missions export <mission_uuid> --format pdf

# Explicit output path
tracelab missions export <mission_uuid> --format docx --output ~/reports/B6.5.docx

# Legacy YAML (backwards-compatible)
tracelab missions export <mission_uuid> --format yaml > mission.yaml
```

- Markdown prints to stdout by default; passing `--output` writes the file instead.
- PDF/DOCX formats always write to disk. If `--output` is omitted the CLI uses the filename suggested
  by the API response (for example `B6.5-report.pdf`).
- JSON mode returns metadata such as `{ "file": "/tmp/B6.5.pdf", "format": "pdf" }` after a file export.

## Mission UI Export Control

On the mission detail page (`/missions/[id]`) a “Report Export” card now offers:

1. Format selector (Markdown, PDF, DOCX).
2. Export button that calls the backend endpoint with the user’s bearer token.
3. Inline error messaging if the download fails.

The download uses the filename provided by the API, ensuring UI, CLI, and automation scripts stay in sync.

## Operational Checklist

1. Run `pytest tests/test_report_export.py tests/integration/test_mission_api.py` to validate the service and API surfaces.
2. Rebuild the frontend (`npm run build`) when distributing static assets so the new export controls ship with the UI bundle.
3. Document exports or telemetry outcomes inside the mission record (e.g., via `mission_runtime` helpers) whenever an agent completes a research deliverable.

## Troubleshooting

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| `PDF export requires reportlab` | Missing dependency | `pip install reportlab` or install project requirements. |
| CLI prints binary data to terminal | Ran `--format pdf/docx` without `--output` | Re-run with `--output` path (required for binary formats). |
| UI button reports “Unauthorized” | Missing/expired auth token | Re-authenticate via the login form before retrying the export. |

