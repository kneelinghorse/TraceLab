# Ingestion & Onboarding Runbook

This runbook captures the minimal operational procedures for the Markdown ingestion workflow delivered in Sprint 02.

## Happy Path

1. Provision a project using the database or onboarding API.
2. Execute `scripts/ingest_cli.py --offline <file> <project_id>` during development, or point the CLI at the deployed API.
3. Monitor `ingestion_chunks_processed{content_type="markdown"}` to confirm throughput.
4. Generate a parity report via `scripts/verify_ingestion_parity.py <document_id>` and archive the JSON artifact.

## Recovery

- **Ingestion stalls**: Inspect the Markdown watcher logs, restart the worker, then re-run the CLI. Verify dashboards refresh within five minutes.
- **Qdrant failures**: Check network connectivity, ensure API keys are configured, then replay the parity script to validate payloads.
- **Coverage drift**: Regenerate the coverage report by reprocessing documents through the existing ingestion pipeline service.

## References

- CLI: `scripts/ingest_cli.py`
- Parity artifacts: `artifacts/ingestion-parity/`
- Observability configs: `infra/observability/ingestion/`
