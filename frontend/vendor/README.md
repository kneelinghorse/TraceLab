# OODS Forge packages

These immutable tarballs are the built `@oods/tokens` and `@oods/tw-variants`
packages captured from the local OODS Forge checkout. They are committed because
the packages are not available from this environment's npm registry and Railway
must install the same artifacts as local development. `oods-provenance.json`
records the checkout, SHA-256 hashes, and clean-install smoke result.

Refresh deliberately from Forge using `npm pack --ignore-scripts`, verify the
CSS scopes and Tailwind generation in a clean tarball install, update provenance,
then run `npm install` here to update the lockfile. Do not point production
dependencies at a developer's sibling checkout.

The Tailwind plugin is a default ESM export and a direct CommonJS export. Its
README's named `createContextVariantsPlugin` example does not match the shipped
interface. TraceLab imports the default export.

## Re-pin acceptance

Consume only a certified Forge bundle from a merged, named commit. A completed
builder mission or a prepared tarball on a review branch is not certification.
Forge owns review and fixes; TraceLab owns the consumer install and smoke.

1. Read the bundle's certification and confirm its commit is merged into Forge's
   accepted branch. In that checkout, build the packages with Forge's documented
   commands, then run `npm pack --ignore-scripts` in `packages/tokens` and
   `packages/tw-variants` (or use the certified bundle's matching packed artifacts).
2. Copy the immutable tarballs into `frontend/vendor/`. Record the full checkout
   hash, each tarball's SHA-256 and byte length in `oods-provenance.json`.
3. Install the tarballs in a clean throwaway directory. Verify Brand A light,
   dark and hc semantic CSS scopes and Tailwind generation using the packaged
   plugin. The `base` CSS selector aliases Light; it is not a fourth palette.
4. Run `npm install` in `frontend/`, commit the lockfile with the tarballs and
   provenance, then run unit tests, `check:tokens`, lint, and the production build.
5. Run `scripts/ui-shell-smoke.mjs` against the built app and deployed site in
   light/dark/hc at 1440/390. Archive screenshots and results with the mission.

THEME-1 keeps `hc` on a light native `color-scheme` so system colors do not
silently follow the OS. Only the Dark theme sets the compatibility `.dark` class;
Tailwind color variants are retired and `check:tokens` rejects new ones. Markdown
typography uses semantic prose variables, with no inversion exception.
