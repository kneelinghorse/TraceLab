# Vendored schemas

Schemas copied verbatim from upstream repositories so the build is hermetic
and we have a git-visible record of exactly which version we're consuming.

When a schema's upstream changes, re-vendor by running the copy command
below, bump the pin here, and either coordinate the rollout with the
upstream team or run the end-to-end contract test against the upstream PR.

| Schema | Upstream path | Pinned to | Vendored on | Consumer |
|---|---|---|---|---|
| `expected_output_schema.schema.json` | `deepsearch/mission/schemas/expected_output_schema.schema.json` in [DeepSearch.alpha] | `ecf0c8b7c9bfbc162683b0a4e6b0e766de7d6e28` | 2026-04-22 | Sprint 40 T40.4 contract-preview integration |

[DeepSearch.alpha]: https://github.com/kneelinghorse/DeepSearch.alpha

## Re-vendoring

```bash
# From TraceLab repo root, assuming DeepSearch.alpha is cloned at the
# adjacent path referenced in the table above.
DS_REPO=/Users/systemsystems/portfolio/DeepSearch.alpha
cp "$DS_REPO/deepsearch/mission/schemas/expected_output_schema.schema.json" \
   schemas/expected_output_schema.schema.json

# Capture the new pin
git -C "$DS_REPO" rev-parse HEAD
```

Update the table above with the new SHA and the vendor date in the same PR
as the schema update.
