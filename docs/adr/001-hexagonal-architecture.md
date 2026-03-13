# ADR 001: Hexagonal Architecture (Ports & Adapters)

## Status
Accepted

## Context
TraceLab has ~60 services with implicit interfaces. Services directly instantiate dependencies, making it hard to test in isolation or swap implementations. As the codebase grows toward agentic workflows, we need clear boundaries between business logic and infrastructure.

## Decision
Adopt hexagonal architecture using `app/ports/` for interface contracts and `app/adapters/` for concrete implementations. Existing services are wrapped (not rewritten) by thin adapter classes that delegate to the original code.

## Consequences
- **Positive:** Services can be tested with mock ports instead of real databases/APIs. New implementations (e.g., different vector DB) slot in without touching business logic.
- **Positive:** Gradual migration — existing `get_*_service()` factories remain for backward compatibility.
- **Negative:** Additional indirection layer. Mitigated by keeping adapters thin (pure delegation).
