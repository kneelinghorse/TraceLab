# TraceLab Schemas

TraceLab Schemas exposes the Mission Protocol Pydantic models as a standalone
package that DeepSearch and other partners can install to pre-validate payloads
before calling the TraceLab API.

## Installation

```bash
pip install -e ./tracelab_schemas
# or from a wheel/sdist packaged via `python -m build tracelab_schemas`
```

The package targets Python 3.11+ and requires `pydantic>=2.6,<3.0`.

## Usage

```python
from tracelab_schemas import MissionProtocolComplete

payload = {...}  # Mission Protocol JSON
mission = MissionProtocolComplete.model_validate(payload)
```

All Mission Protocol types are exported at the package root, matching the names
found in TraceLab (`MissionProtocolDraft`, `MissionProtocolComplete`,
`ResearchStatement`, `MethodologyDetails`, etc.).

## Versioning

The version defined in `tracelab_schemas/tracelab_schemas/version.py` is the
single source of truth. Increment the version whenever the schema changes and
publish a new wheel. `app/models/mission_protocol.py` imports directly from this
package so TraceLab and DeepSearch always share the same schema definitions.

See `docs/schema-package.md` for a detailed release workflow and parity checks.
