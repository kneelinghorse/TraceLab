# Testing & Documentation Best Practices

These guardrails complement the architectural baselines in `foundational-docs/tech_arch_template.md` and apply to every Sprint 04 mission.

## Testing Strategy
- **Layered coverage**: pair service-level unit tests (e.g., `tests/test_embedding_generation.py`) with integration suites under `tests/integration/` to keep traceability between APIs and Mission Protocol.
- **Parity enforcement**: run `python cmos/scripts/validate_parity.py --check` before and after significant changes to confirm SQLite ↔ file mirrors stay in sync.
- **Benchmarking**: execute `pytest tests/performance/test_concurrent_queries.py --benchmark-only` whenever cache, retrieval, or OpenAI routing code changes.
- **Coverage reporting**: publish `cmos/reports/sprint-04/test-coverage-report.html` from `pytest --cov=app --cov-report=html:cmos/reports/sprint-04/htmlcov` for every sprint review.

## Documentation Workflow
- Keep `docs/README.md` as the navigation index for onboarding material, tutorials, and API references.
- Reference canonical templates (`foundational-docs/roadmap_template.md` and the tech-arch template) instead of duplicating long-form plans.
- Update Mission Protocol user guides in lockstep with schema or API adjustments so `/docs` and `/openapi.json` stay authoritative.

## Telemetry & Quality Gates
- All RAG queries should emit cost + cache telemetry via `app/services/cost_monitor.py`; integration tests now assert that behavior.
- Mission completion notes must include `summary` + `next_hint` fields so orchestration workers can promote the next backlog item automatically.
- The `cmos/context/MASTER_CONTEXT` should only be mutated via `context.db_client.SQLiteClient` helpers to preserve audit history.
