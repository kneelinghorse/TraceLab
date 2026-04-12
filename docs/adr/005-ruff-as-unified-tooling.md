# ADR 005: Ruff as Unified Python Tooling

## Status
Accepted

## Context
The project had no automated linting or formatting. The traditional stack (black + flake8 + isort) requires three tools with separate configs. Ruff provides linting, formatting, and import sorting in a single tool with 10-100x speed improvement.

## Decision
Adopt ruff as the sole Python linting and formatting tool. Configure in `pyproject.toml` under `[tool.ruff]`. Enforce via pre-commit hooks and CI.

## Consequences
- **Positive:** Single tool, single config. Sub-second linting on the full codebase.
- **Positive:** Drop-in replacement for flake8 rules with additional checks (bugbear, simplify, security).
- **Negative:** Less ecosystem familiarity than black/flake8 combo. Mitigated by ruff's rapid adoption and compatibility.
