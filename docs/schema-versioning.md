# Schema Versioning and Release Process

This document describes the versioning policy, release workflow, and cross-system
version alignment for the `tracelab-schemas` package.

## Semantic Versioning

The package follows [Semantic Versioning 2.0.0](https://semver.org/):

| Bump  | When to Use                                           | Example          |
|-------|-------------------------------------------------------|------------------|
| MAJOR | Breaking changes to `MissionProtocolComplete` schema  | 1.0.0 → 2.0.0    |
| MINOR | New optional fields, new schema types                 | 1.0.0 → 1.1.0    |
| PATCH | Bug fixes, documentation, no schema changes           | 1.0.0 → 1.0.1    |

### What Constitutes a Breaking Change?

**Breaking (MAJOR bump required):**
- Removing a required field from `MissionProtocolComplete`
- Changing a field type (e.g., `str` → `int`)
- Renaming a required field
- Adding a new required field without a default
- Changing validation rules that reject previously valid payloads

**Non-breaking (MINOR bump):**
- Adding optional fields with defaults
- Adding new schema types (e.g., `NewModelType`)
- Relaxing validation (accepting more input formats)
- Adding new enum values

**No schema change (PATCH bump):**
- Fixing validation bugs
- Updating documentation
- Improving error messages
- Refactoring without behavior change

## Release Workflow

### 1. Prepare the Release

```bash
# Bump version (choose: major, minor, patch, or explicit version)
./scripts/bump-version.sh minor

# This updates tracelab_schemas/tracelab_schemas/version.py
```

### 2. Update CHANGELOG

Edit `tracelab_schemas/CHANGELOG.md`:

```markdown
## [1.1.0] - 2025-12-10

### Added
- New `ConfidenceScore` field on `EvidenceItem` (optional)

### Changed
- Improved validation error messages for `synthesis` field
```

### 3. Commit and Tag

```bash
git add tracelab_schemas/
git commit -m "chore: bump tracelab-schemas to 1.1.0"

git tag schemas-v1.1.0
git push origin schemas-v1.1.0
```

### 4. Automated Publishing

Pushing the tag triggers the GitHub Actions workflow:

1. **Validate** - Verifies tag matches `version.py`
2. **Build** - Creates wheel and sdist
3. **Publish** - Uploads to GitHub Packages
4. **Release** - Creates GitHub Release with changelog

## Installing from GitHub Packages

### Authentication Setup

Create a Personal Access Token (PAT) with `read:packages` scope:

```bash
# Add to pip config or environment
export PIP_INDEX_URL=https://__token__:${GITHUB_TOKEN}@pypi.pkg.github.com/systemsystems/simple
```

Or in `~/.pip/pip.conf`:

```ini
[global]
index-url = https://pypi.org/simple
extra-index-url = https://__token__:${GITHUB_TOKEN}@pypi.pkg.github.com/systemsystems/simple
```

### Install the Package

```bash
# Latest version
pip install tracelab-schemas

# Specific version
pip install tracelab-schemas==1.0.0

# With explicit index
pip install tracelab-schemas --extra-index-url https://pypi.pkg.github.com/systemsystems
```

### In requirements.txt

```txt
# Use --extra-index-url in pip command
tracelab-schemas>=1.0.0,<2.0.0
```

## Cross-System Version Alignment

TraceLab and DeepSearch must use compatible schema versions to ensure
payloads are validated consistently.

### CI Version Check

The `version-check.yml` workflow runs on PRs that modify:
- `tracelab_schemas/` (schema package)
- `requirements*.txt` (dependencies)
- `pyproject.toml` (project config)

It validates:
1. Version follows semver format
2. CHANGELOG has entry for new version
3. Breaking changes are documented (for major bumps)
4. Schema models load without errors

### Version Compatibility Matrix

| TraceLab | DeepSearch | Compatible | Notes                     |
|----------|------------|------------|---------------------------|
| 1.0.x    | 1.0.x      | ✅ Yes     | Exact match recommended   |
| 1.0.x    | 1.1.x      | ✅ Yes     | Minor bump is compatible  |
| 1.0.x    | 2.0.x      | ❌ No      | Major bump = breaking     |

### Pinning Versions

**TraceLab** should pin to a minimum compatible version:

```toml
# pyproject.toml
dependencies = [
  "tracelab-schemas>=1.0.0,<2.0.0"
]
```

**DeepSearch** should use the same version constraint:

```txt
# requirements.txt
tracelab-schemas>=1.0.0,<2.0.0
```

## Breaking Change Protocol

Before releasing a MAJOR version bump:

### 1. Deprecation Notice (Prior Version)

Add deprecation warnings in the current version:

```python
# In mission_protocol.py
import warnings

@field_validator('old_field')
def deprecate_old_field(cls, v):
    warnings.warn(
        "old_field is deprecated and will be removed in v2.0.0. "
        "Use new_field instead.",
        DeprecationWarning
    )
    return v
```

### 2. Document in CHANGELOG

```markdown
## [1.x.x] - Date

### Deprecated
- `old_field` on `MissionProtocolComplete` - use `new_field` instead
  (will be removed in 2.0.0)
```

### 3. Coordinate with DeepSearch Team

- Notify DeepSearch team of upcoming breaking change
- Provide migration timeline (minimum 2 weeks)
- Share migration guide
- Get acknowledgment before releasing

### 4. Migration Guide

Include in CHANGELOG for the major version:

```markdown
## [2.0.0] - Date

### BREAKING CHANGES
- Removed `old_field` from `MissionProtocolComplete`
- Changed `score` field type from `str` to `float`

### Migration Guide

**old_field removal:**
```python
# Before (v1.x)
mission.old_field = "value"

# After (v2.x)
mission.new_field = "value"
```

**score type change:**
```python
# Before (v1.x)
payload = {"score": "0.85"}

# After (v2.x)
payload = {"score": 0.85}
```
```

## Local Development

### Editable Install

```bash
pip install -e ./tracelab_schemas
```

### Running Tests

```bash
pytest tracelab_schemas/tests/
```

### Building Locally

```bash
cd tracelab_schemas
python -m build
# Creates dist/tracelab_schemas-1.0.0.tar.gz and .whl
```

### Dry Run (Test Publish)

The publish workflow doesn't support dry-run, but you can test locally:

```bash
# Build
python -m build tracelab_schemas/

# Check package
twine check tracelab_schemas/dist/*
```

## Troubleshooting

### Version Mismatch Error

If CI reports version mismatch:

```
ERROR: Tag version (1.1.0) does not match package version (1.0.0)
```

Solution: Update `version.py` before tagging:

```bash
./scripts/bump-version.sh 1.1.0
git add tracelab_schemas/
git commit --amend  # Add to tag commit
git tag -f schemas-v1.1.0
git push -f origin schemas-v1.1.0
```

### Package Not Found

If `pip install tracelab-schemas` fails:

1. Check authentication token has `read:packages` scope
2. Verify package was published (check GitHub Packages page)
3. Try explicit index URL:
   ```bash
   pip install tracelab-schemas --index-url https://pypi.pkg.github.com/systemsystems
   ```

### Import Error After Upgrade

If imports fail after version upgrade:

1. Check for breaking changes in CHANGELOG
2. Verify you have the correct version installed:
   ```python
   from tracelab_schemas import __version__
   print(__version__)
   ```
3. Follow migration guide for major version upgrades

## References

- [Schema Package Distribution Guide](./schema-package.md)
- [DeepSearch Integration Contract](../cmos/planning/DeepSearch-TraceLab-Integration-Contract.md)
- [CHANGELOG](../tracelab_schemas/CHANGELOG.md)
- [Semantic Versioning Spec](https://semver.org/)
