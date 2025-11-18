# Schema Package Distribution Guide

The `tracelab_schemas` package exposes the TraceLab Mission Protocol Pydantic
schemas as a reusable library so DeepSearch can pre-validate payloads prior to
submitting them to the TraceLab API.

## Layout

```
tracelab_schemas/
├── pyproject.toml
├── README.md
├── tracelab_schemas/
│   ├── __init__.py
│   ├── mission_protocol.py
│   ├── version.py
│   └── py.typed
└── tests/
    └── test_schemas.py
```

`mission_protocol.py` is the canonical source for all Pydantic models.
`app/models/mission_protocol.py` now re-exports these models to guarantee that
TraceLab and partner scripts stay in lock-step.

## Versioning Policy

1. Update `tracelab_schemas/tracelab_schemas/version.py` when models change.
2. Record the version change in the mission or changelog entry that introduced
   the schema update.
3. Re-run `pytest tracelab_schemas/tests` to validate the package locally.
4. Rebuild the package via `python -m build tracelab_schemas`.
5. Publish/upload the new wheel (PyPI, Artifactory, or shared drive) and notify
   DeepSearch so they can upgrade.

The TraceLab app imports these schemas from the package (with a fallback to the
source directory), so the same version is used for runtime validation, parity
checks, and DeepSearch tooling.

## Installation

Developers can install directly from the repo root:

```bash
pip install -e ./tracelab_schemas
```

DeepSearch can consume a wheel/sdist artifact generated from `python -m build`.
Because `py.typed` is included, downstream projects receive type information.

## Validation Checklist

- [ ] `pytest tracelab_schemas/tests`
- [ ] `pytest tests/test_mission_protocol_validation.py` (TraceLab integration)
- [ ] `python cmos/scripts/validate_foundational_refs.py`
- [ ] `python cmos/scripts/validate_parity.py --check`

Capture test outputs in the mission telemetry summary upon completion.
