import { expect, test } from "@playwright/test";

/**
 * Contrast is measured here, not assumed.
 *
 * axe only reports contrast for element/state combinations a fixture actually renders, so
 * states that no fixture happens to produce -- a viewed activity row, a disabled control,
 * muted helper text on a raised panel -- can regress without any spec going red. This reads
 * the resolved token values out of a real page in each theme and checks every text-on-surface
 * pair the app actually composes (A11Y-1).
 */

/** WCAG 2.1 relative luminance and contrast ratio. */
function ratio(a: [number, number, number], b: [number, number, number]) {
  const luminance = (rgb: [number, number, number]) =>
    0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2]);
  const light = Math.max(luminance(a), luminance(b));
  const dark = Math.min(luminance(a), luminance(b));
  return (light + 0.05) / (dark + 0.05);
}
function channel(value: number) {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}
/** The OODS tokens are authored in CIE Lab, so the browser converts them to sRGB for us.
 *  Reading the numbers out of `lab(...)` and treating them as channels reports ~1.2:1 for
 *  every pair, which looks like total failure and is really a unit error. */
function parse(rgb: [number, number, number]): [number, number, number] {
  return rgb;
}

const SURFACES = ["canvas", "raised", "subtle"] as const;
// Text tokens that render as normal-size body text, so AA is 4.5:1.
const BODY_TEXT = ["primary", "secondary", "muted", "accent"] as const;

const PAIRS: { text: string; surface: string; note?: string }[] = [
  ...SURFACES.flatMap(surface => BODY_TEXT.map(text => ({ text: `text-${text}`, surface: `surface-${surface}` }))),
  { text: "text-inverse", surface: "surface-inverse", note: "skip link and inverted chips" },
  { text: "text-on-interactive", surface: "surface-interactive-primary-default", note: "primary button rest" },
  { text: "text-on-interactive", surface: "surface-interactive-primary-hover", note: "primary button hover" },
  { text: "text-on-interactive", surface: "surface-interactive-primary-pressed", note: "primary button pressed" },
];

for (const theme of ["light", "dark"] as const) {
  test(`every body text token meets AA against every surface it is used on (${theme})`, async ({ page }) => {
    await page.addInitScript(t => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test", display_name: "Researcher" }));
      localStorage.setItem("tracelab.theme.v1:reader", t);
    }, theme);
    await page.emulateMedia({ colorScheme: theme });
    await page.route("**/api/v1/**", route => route.fulfill({ json: {} }));
    await page.goto("/");
    await expect(page.locator("body")).toBeVisible();

    const measured = await page.evaluate(pairs => {
      const probe = document.createElement("span");
      probe.style.display = "none";
      document.body.append(probe);
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 1;
      const context = canvas.getContext("2d", { willReadFrequently: true })!;
      // Round-trip through a canvas so ANY colour space the tokens use (they are Lab today)
      // comes back as sRGB, instead of being parsed as if it were already rgb().
      const resolve = (token: string): [number, number, number] => {
        probe.style.color = `var(--theme-${token})`;
        context.clearRect(0, 0, 1, 1);
        context.fillStyle = getComputedStyle(probe).color;
        context.fillRect(0, 0, 1, 1);
        const [r, g, b] = context.getImageData(0, 0, 1, 1).data;
        return [r, g, b];
      };
      const out = pairs.map(pair => ({ ...pair, textColor: resolve(pair.text), surfaceColor: resolve(pair.surface) }));
      probe.remove();
      return { theme: document.documentElement.dataset.theme, pairs: out };
    }, PAIRS);

    expect(measured.theme).toBe(theme);

    const failures = measured.pairs
      .map(pair => ({ ...pair, contrast: Number(ratio(parse(pair.textColor), parse(pair.surfaceColor)).toFixed(2)) }))
      .filter(pair => pair.contrast < 4.5)
      .map(pair => `${pair.text} on ${pair.surface}: ${pair.contrast}:1${pair.note ? ` (${pair.note})` : ""}`);

    expect(failures, `AA requires 4.5:1 for normal text in the ${theme} theme`).toEqual([]);
  });
}

test("the disabled pair is measured and reported, not silently trusted", async ({ page }) => {
  // WCAG 1.4.3 exempts inactive controls, so this does NOT gate on 4.5:1. It exists so the
  // value is recorded rather than assumed, and so a change to it is visible in the diff.
  await page.addInitScript(() => localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test", display_name: "Researcher" })));
  await page.route("**/api/v1/**", route => route.fulfill({ json: {} }));
  await page.goto("/");
  const colors = await page.evaluate(() => {
    const probe = document.createElement("span");
    probe.style.display = "none";
    document.body.append(probe);
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const context = canvas.getContext("2d", { willReadFrequently: true })!;
    const resolve = (token: string): [number, number, number] => {
      probe.style.color = `var(--theme-${token})`;
      context.clearRect(0, 0, 1, 1);
      context.fillStyle = getComputedStyle(probe).color;
      context.fillRect(0, 0, 1, 1);
      const [r, g, b] = context.getImageData(0, 0, 1, 1).data;
      return [r, g, b];
    };
    const out = { text: resolve("text-disabled"), surface: resolve("surface-disabled") };
    probe.remove();
    return out;
  });
  const contrast = ratio(parse(colors.text), parse(colors.surface));
  console.log(`text-disabled on surface-disabled: ${contrast.toFixed(2)}:1 (WCAG-exempt, recorded)`);
  expect(contrast).toBeGreaterThan(1);
});
