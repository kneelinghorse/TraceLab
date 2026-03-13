# ADR 003: FastAPI Depends() as Dependency Injection

## Status
Accepted

## Context
The codebase needs a way to wire port interfaces to concrete adapters. Options include a DI container library (e.g., python-inject, dependency-injector) or FastAPI's built-in `Depends()` mechanism.

## Decision
Use FastAPI `Depends()` with factory functions in `app/dependencies.py` as the composition root. No external DI library.

## Consequences
- **Positive:** Zero new dependencies. FastAPI developers already understand `Depends()`.
- **Positive:** Easy to override in tests via `app.dependency_overrides`.
- **Negative:** Only works within FastAPI request context. Background tasks or CLI commands need direct instantiation. Mitigated by keeping factory functions importable standalone.
