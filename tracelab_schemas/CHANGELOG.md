# Changelog

All notable changes to the `tracelab-schemas` package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Versioning Policy

- **MAJOR**: Breaking changes to `MissionProtocolComplete` or `MissionProtocolDraft` schemas
- **MINOR**: New optional fields, new schema types, backward-compatible additions
- **PATCH**: Bug fixes, documentation updates, no schema changes

### Breaking Change Protocol

Before releasing a MAJOR version:
1. Document breaking changes in this file under `### BREAKING CHANGES`
2. Provide migration guide for downstream consumers
3. Notify DeepSearch team at least 1 version prior (deprecation notice)
4. Both teams must acknowledge before release

---

## [Unreleased]

### Added
- Nothing yet

### Changed
- Nothing yet

### Deprecated
- Nothing yet

### Removed
- Nothing yet

### Fixed
- Nothing yet

---

## [1.0.0] - 2025-12-05

### Added
- Initial release of `tracelab-schemas` package
- `MissionProtocolComplete` - Full mission schema with all required fields
- `MissionProtocolDraft` - Partial mission schema for work-in-progress
- `ResearchStatement` - Research objective and scope definition
- `KeyQuestion` - Question tracking with answer status
- `Synthesis` - Key insights, recommendations, and next steps
- `EvidenceItem` - Source evidence with URL and content
- `QualityCheckpoint` - Quality gate validation records
- `MethodologyDetails` - Research methodology documentation
- GitHub Packages publishing workflow
- Semantic versioning with CI validation
- Version alignment checks for cross-system parity

### Technical Details
- Python 3.11+ required
- Pydantic v2.5+ for validation
- Type hints with `py.typed` marker
- Apache 2.0 license

---

## Version History Summary

| Version | Date       | Type    | Description                          |
|---------|------------|---------|--------------------------------------|
| 1.0.0   | 2025-12-05 | Initial | Mission Protocol schemas for DeepSearch |

---

## Migration Guides

### Migrating to 1.0.0

This is the initial release. No migration needed.

**Installation:**
```bash
pip install tracelab-schemas==1.0.0 \
  --index-url https://pypi.pkg.github.com/systemsystems
```

**Basic usage:**
```python
from tracelab_schemas import MissionProtocolComplete

mission = MissionProtocolComplete.model_validate(payload)
```

---

[Unreleased]: https://github.com/systemsystems/TraceLab/compare/schemas-v1.0.0...HEAD
[1.0.0]: https://github.com/systemsystems/TraceLab/releases/tag/schemas-v1.0.0
