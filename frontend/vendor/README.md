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
