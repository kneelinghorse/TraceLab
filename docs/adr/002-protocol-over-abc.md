# ADR 002: typing.Protocol Over abc.ABC

## Status
Accepted

## Context
Port interfaces need to define contracts that existing services can satisfy. Python offers two approaches: `abc.ABC` (nominal subtyping requiring explicit inheritance) and `typing.Protocol` (structural subtyping where any class with matching methods conforms automatically).

## Decision
Use `typing.Protocol` for all port definitions. Existing services that already have matching method signatures conform without modification — no inheritance changes needed.

## Consequences
- **Positive:** Zero changes to existing service classes. Functional-programming-friendly (no class hierarchy).
- **Positive:** Mypy validates conformance at type-check time without runtime overhead.
- **Negative:** Protocol conformance is less explicit — developers must check method signatures manually. Mitigated by mypy enforcement on `app/ports/`.
