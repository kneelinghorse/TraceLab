# TraceLab Schemas

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.11+-green.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

TraceLab Schemas exposes the Mission Protocol Pydantic models as a standalone
package that DeepSearch and other partners can install to pre-validate payloads
before calling the TraceLab API.

## Installation

### From GitHub Packages (Recommended)

```bash
# Set up authentication (one-time setup)
export GITHUB_TOKEN="your_personal_access_token"

# Install latest version
pip install tracelab-schemas \
  --extra-index-url https://__token__:${GITHUB_TOKEN}@pypi.pkg.github.com/systemsystems/simple

# Install specific version
pip install tracelab-schemas==1.0.0 \
  --extra-index-url https://__token__:${GITHUB_TOKEN}@pypi.pkg.github.com/systemsystems/simple
```

### From Source (Development)

```bash
# Editable install from repo
pip install -e ./tracelab_schemas

# Build wheel/sdist
python -m build tracelab_schemas
pip install tracelab_schemas/dist/tracelab_schemas-*.whl
```

### Requirements

- Python 3.11+
- `pydantic>=2.5,<3.0`

## Usage

```python
from tracelab_schemas import MissionProtocolComplete

payload = {...}  # Mission Protocol JSON
mission = MissionProtocolComplete.model_validate(payload)
```

All Mission Protocol types are exported at the package root:

- `MissionProtocolComplete` - Full mission with all required fields
- `MissionProtocolDraft` - Partial mission for work-in-progress
- `ResearchStatement` - Research objective and scope
- `KeyQuestion` - Question with answer tracking
- `Synthesis` - Key insights and recommendations
- `EvidenceItem` - Source evidence with URL/content
- `QualityCheckpoint` - Quality gate validation
- `MethodologyDetails` - Research methodology

## Type Hints

The package includes `py.typed` marker for full type hint support:

```python
from tracelab_schemas import MissionProtocolComplete

def validate_mission(data: dict) -> MissionProtocolComplete:
    return MissionProtocolComplete.model_validate(data)
```

## Versioning

This package follows [Semantic Versioning](https://semver.org/):

| Bump  | When                                    |
|-------|-----------------------------------------|
| MAJOR | Breaking changes to required fields     |
| MINOR | New optional fields or schema types     |
| PATCH | Bug fixes, documentation only           |

The version in `tracelab_schemas/version.py` is the single source of truth.
TraceLab and DeepSearch must use compatible versions (same major version).

### Checking Version

```python
from tracelab_schemas import __version__
print(__version__)  # e.g., "1.0.0"
```

## Integration with TraceLab

`app/models/mission_protocol.py` imports from this package, ensuring
TraceLab and DeepSearch always use the same schema definitions.

## Documentation

- [CHANGELOG](CHANGELOG.md) - Version history and migration guides
- [Schema Versioning Guide](../docs/schema-versioning.md) - Release process
- [Schema Package Guide](../docs/schema-package.md) - Package structure
- [DeepSearch Integration](../docs/deepsearch-integration.md) - API usage

## Development

```bash
# Install with dev dependencies
pip install -e "./tracelab_schemas[dev]"

# Run tests
pytest tracelab_schemas/tests/

# Bump version
./scripts/bump-version.sh minor
```

## License

Apache 2.0 - see [LICENSE](../LICENSE) for details.
