# TraceLab production configuration

This named partial (`tracelab`) owns only `service.TraceLab` and
`service.frontend` in project `4e3adf39-f05e-48f8-8c7c-f2f27621b484`, environment
`4fb80245-6762-4438-ab94-6993c3568a92`. The authoring guard rejects other targets.
DeepSearch, Postgres, Qdrant, and their volumes are outside this partial.

Install the pinned SDK with `npm ci` at the repository root. Use Railway CLI
5.63.1 or a compatible later version with named partials and pinned plans.
The CLI is an operator tool, not an application dependency. The local package
file selects ESM only for this directory; root tooling remains CommonJS.

Link the exact production project/environment, inspect ownership with
`railway config partials list --json`, and review `railway config plan` before
applying. Commit `.railway/` before creating a pinned plan:

```sh
railway config plan --out /tmp/tracelab-railway-plan.json
railway config apply --plan /tmp/tracelab-railway-plan.json --yes
```

Do not use `--confirm-destructive` for this migration. Re-plan if the environment
etag or authoring tree changes. Preserve existing variable values with
`preserve()`; never decrypt/import secret values. Future variable additions must
also be represented here before applying this partial again.

Railway does not read `.railway/` during application deployments. Configuration
changes require the explicit plan/apply operation; ordinary source changes deploy
from `main` as before. No new CI credential is required by this manual workflow.

## Sprint 62 migration order and rollback

The baseline and reviewed diff are in `cmos/reports/sprint-62/S62-DEPLOY/`.
The active deployment manifests are authoritative for behavior: the backend
actually uses `/Dockerfile`, despite its legacy JSON saying Nixpacks; frontend
actually uses Nixpacks and `/admin/users`, despite different dashboard defaults.
Keep Alembic before uvicorn, frontend root `/frontend`, one replica per service,
and the existing region, restart, networking and variable configuration.
Railway normalizes empty watch patterns, sleep=false, and the ON_FAILURE/10 restart
defaults out of its imported graph. These defaults remain verified in live service
readback; replica count is represented once in `multiRegionConfig`. Omitting the
redundant declarations makes the post-apply plan empty. The backend's legacy
`serviceInstance.builder` field still reports RAILPACK; the IaC environment graph
and actual deployment manifest carry DOCKERFILE and `/Dockerfile`.

1. Capture active deployment manifests, dashboard settings, domains, volumes,
   source triggers and ownership. Both custom config path settings were already
   null; legacy files were auto-discovered in the repository.
2. Apply the reviewed, pinned partial that materializes those effective settings.
   CLI 5.63.1 accepts this plan with the auto-discovered files still present.
   Read back effective settings and ownership before removing either file.
3. Remove root/frontend `railway.json` only after the equivalent live settings
   exist. Merge the validated source revision and verify both actual deployments,
   resolved config source, Alembic logs, serving hashes and authenticated smoke.
4. A fresh plan must have no configuration drift; compare unrelated resources
   and all variable names/presence against the baseline.

Before source rollout, rollback can release only the `tracelab` partial and restore
the two services' previous dashboard settings from `inventory-before.json`.
The still-present legacy files continue supplying their existing effective values.
After rollout, prefer restoring the prior source revision while retaining the
equivalent supported configuration. The previous successful deployments were
backend `92ce8d71-8095-4dde-a112-c7b1bb8c185d` and frontend
`af496e92-c85e-4a7f-8ad3-e42b3ec36ae4`, both serving
`4495119551c67a39b393b40f0e0d176ea84128ba`.

Returning to legacy files is only a temporary fallback before **2026-12-01**:
release the two owned addresses, restore files from the previous revision and
restore dashboard settings; verify the resulting deployments. Do not release
other partials, delete resources, or change database/volume/domain identities.

References: [Railway migration and ownership](https://docs.railway.com/infrastructure-as-code),
[legacy cutoff](https://docs.railway.com/config-as-code).
