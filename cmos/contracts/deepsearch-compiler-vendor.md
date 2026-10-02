# DeepSearch Contract Compiler — Vendoring & Resync Ritual

TraceLab compiles structural previews locally because DeepSearch runs a polling
worker, not a deployed preview HTTP service. This is the vendor contract; the
[field map](mission-authoring-contract.md) owns authoring/storage boundaries.
Guiding template: [technical architecture](../foundational-docs/tech_arch_template.md).

## Pinned source and fidelity

- Repository: DeepSearch.alpha; branch `codex/s94-authored-scope`.
- Immutable implementation: `79ef84842fb84259bafe59924b21fe2f5ad05d7d`.
- Schema **1.2**, semantic compiler revision **3**. A source commit and a
  semantic revision are different identities.
- Local adaptation/source hashes: `app/services/contract_compiler/vendor-manifest.json`.
- Canonical fixtures: `tests/fixtures/authored_scope_v1/`, copied byte for byte
  from that commit, including the upstream manifest. Manifest SHA-256:
  `db256e5821393ca9750b704714b8e76803e3e8f7de86255a6f83d9d7cc0114cc`.
- Canonical contract: `8ca1ebfaa604dc7e`; full canonical JSON SHA-256:
  `163e7af36080b8440afe55f501b023cb2e3aba84e1b8644298fc0784167b5cb6`.

Fidelity remains **structural_only**. This pin reproduces the immutable offline
fixture, not an unverified deployed worker, configured model enrichment or the
missing historical execution `bae1333274533285`. The separate historical preview
`106cb8668a3efdb8` is not this canonical fixture. No paid run is needed for local
parity; production byte identity requires a separately authorized required run.

## Complete structural source set

| Upstream path | Local module under `app/services/contract_compiler/` |
| --- | --- |
| `deepsearch/mission/contract.py` | `contract.py` |
| `deepsearch/mission/scope.py` | `scope.py` |
| `deepsearch/mission/compiler_provenance.py` | `compiler_provenance.py` |
| `deepsearch/mission/title_utils.py` | `title_utils.py` |
| `deepsearch/agent/deliverable_schemas.py` | `deliverable_schemas.py` |
| `deepsearch/domain_policy.py` | `domain_policy.py` |

The facade `__init__.py` and preview adapter are TraceLab-owned. Only pure
structural dependencies are vendored; no worker, actor, model, telemetry or
observability dependency tree is installed.

Local adaptations, enumerated in the manifest:

1. Preserve attribution in each module and rewrite structural imports locally.
2. Every preview passes `enrichment_mode="none"` explicitly. The vendored
   entrypoint also defaults to `none` and rejects `configured`; upstream defaults
   to `configured`. Thus an accidentally installed DeepSearch cannot activate
   providers. Dormant upstream execution/enrichment helpers are not exported by
   the facade or invoked by preview. Empty entities use deterministic extraction;
   declared entities remain authoritative without disambiguation calls.
3. Provenance uses the immutable vendor pin, actual local source hashes and a
   manifest comparison for source dirtiness. It never imports observability or
   discovers host Git/environment build identity. Configured provenance is
   unavailable. Its manifest describes the adapted local implementation, and
   must not be advertised as the upstream runtime's manifest hash.
4. Sort imports and supply `zip(strict=False)` for local lint without semantic
   changes. Legacy upstream typing syntax retains the existing scoped Ruff
   modernization exemptions; correctness rules remain enabled.

## State and canonical identity

Canonical comparison uses the upstream canonical origin/time and no enrichment.
Compare the **entire** canonical JSON; never remove inconvenient fields.
Ordinary preview metadata may identify a preview invocation; canonical identity
is a separately labeled structural comparison, not an executed contract ID.

The pinned worker converter sets `project_id=None` (TraceLab owns association),
`depth_config={}`, baseline depth, default maximum 3 and default minimum **2**.
The adapter now uses minimum 2 instead of its old 0. Explicit author values
remain intact, including 0: the worker currently coerces nonpositive minima to 2,
so an explicitly authored 0 is a documented worker/preview difference, not a
parity claim. Changing worker execution budgets or restoring depth authoring is
outside this resync. The canonical fixture has no such override.

Structured scope belongs in `context.authored_scope`; references alone are
seeds. Only the pinned typed compiler's supported grammar creates restrictions.
Exact pages, domains and numeric bounds retain upstream semantics and validation.

## Resync procedure

Resync when compiler schema/models, semantic inputs, worker row mapping or scope
semantics change. Runtime scheduling/retrieval changes alone do not require it.

1. Read an immutable upstream commit, its docs, worker converter and compiler
   provenance module. Inspect newer delivery evidence separately; never substitute
   a moving HEAD silently. Verify all upstream manifest/fixture hashes first.
2. Copy the six structural modules above using `git show <pin>:<path>` and copy
   fixture bytes into root tests. Audit any new imports before expanding the set.
3. Reapply the enumerated local adaptations. Regenerate upstream/local hashes in
   `vendor-manifest.json`; update the pin here and in the facade. Do not include
   runtime services or configured enrichment dependencies.
4. Test complete canonical bytes, identity sensitivity, legacy missions, typed
   errors before extraction, all eight admission cases, and fresh-process preview
   isolation both without and with a hostile installed DeepSearch sentinel.
5. Run preview/API regressions, changed-file lint and foundational references.
   Preserve any explicit default mismatch in the receipt. Update the field map in
   the same implementation commit when authoring boundaries change.
6. Record a source-bound receipt and prepare any cross-project reply. Sending a
   message and dispatching research each require their own user authorization.

```bash
python -m scripts.check_authored_scope_parity
pytest tests/unit/test_authored_scope_compiler.py tests/test_mission_contract_preview.py tests/test_missions_api.py
python cmos/scripts/validate_foundational_refs.py
```

## Resync log

| Date | Source | Reason |
| --- | --- | --- |
| 2026-04-27 | `24e8810` | T41.1: replace unavailable HTTP proxy with schema 1.0 vendor |
| 2026-10-01 | `79ef848` | S64-VENDOR: six-module schema 1.2/revision 3, authored scope, exact canonical fixture and offline guards |

The prior pending-1.1 gate and three-file recipe are superseded by this verified
1.2 fixture and complete structural module set.
