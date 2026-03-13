# ADR 004: Testcontainers Over SQLite for Integration Tests

## Status
Accepted

## Context
The test suite uses SQLite as a stand-in for PostgreSQL, requiring hacks for computed columns, `jsonb_array_length`, and other PG-specific features. This masks real bugs that only surface in production.

## Decision
Use `testcontainers-python` with PostgreSQL 15 for integration tests. Unit tests use mocked ports (no database at all). The existing SQLite conftest remains during transition so old tests keep running.

## Consequences
- **Positive:** Integration tests exercise real PostgreSQL behavior. No more SQLite compatibility hacks for new tests.
- **Positive:** Unit tests are faster (no DB setup).
- **Negative:** Integration tests require Docker. Mitigated by CI having Docker available and marking tests with `@pytest.mark.integration`.
