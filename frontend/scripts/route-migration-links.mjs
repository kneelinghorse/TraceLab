import migrations from '../src/lib/route-migrations.json' with { type: 'json' };

/**
 * Inspect frontend-origin links without retaining query strings or fragments,
 * which can contain invite/device credentials in authenticated pages.
 * @param {string[]} hrefs
 * @param {string} baseUrl
 */
export function inspectInternalLinks(hrefs, baseUrl) {
  const base = new URL(baseUrl);
  const paths = new Set();
  for (const href of hrefs) {
    try {
      const url = new URL(href, base);
      if (url.origin === base.origin) paths.add(url.pathname);
    } catch { /* An invalid URL cannot point to a legacy application route. */ }
  }
  const aliases = migrations.filter(row => row.kind === 'redirect');
  const internalLinks = [...paths].sort();
  const legacyInternalLinks = internalLinks.flatMap(pathname => aliases
    .filter(row => new RegExp(`^${row.source.replace(/:[^/]+/g, '[^/]+')}/?$`).test(pathname))
    .map(row => ({ pathname, alias: row.source })));
  return { internalLinks, legacyInternalLinks };
}
