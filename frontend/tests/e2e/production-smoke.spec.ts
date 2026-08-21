import { expect, test } from "@playwright/test";

const isProductionSmoke = Boolean(process.env.PLAYWRIGHT_BASE_URL);
const apiBase = (process.env.PLAYWRIGHT_API_BASE_URL ?? "https://api.tracelab.aquex.ai").replace(/\/$/, "");
const apiPrefix = (process.env.PLAYWRIGHT_API_PATH_PREFIX ?? "/api/v1").replace(/\/$/, "");
const reconcilerFreshnessLimitMs = 30 * 60 * 1000;
const allowedClockSkewMs = 60 * 1000;
const buildApiUrl = (path: string) => {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const prefix = apiPrefix ? apiPrefix : "";
  return `${apiBase}${prefix}${normalized}`;
};

test.describe("Production smoke", () => {
  test.skip(!isProductionSmoke, "Set PLAYWRIGHT_BASE_URL to enable production smoke suite.");

  test("missions route responds at the public domain", async ({ page }) => {
    await page.goto("/missions", { waitUntil: "domcontentloaded" });
    await expect(page.locator("main")).toContainText(/Verifying session|Mission Protocol/i);
  });

  for (const route of ["/admin/users", "/admin/spaces"]) {
    test(`${route} is deployed as its own Next page`, async ({ page }) => {
      const response = await page.goto(route, { waitUntil: "domcontentloaded" });
      expect(response?.status()).toBe(200);

      const serialized = await page.locator("#__NEXT_DATA__").textContent();
      expect(serialized).not.toBeNull();
      expect(JSON.parse(serialized ?? "{}").page).toBe(route);
    });
  }

  test("API health endpoint confirms production authorization and reconciler freshness", async ({ request }) => {
    const response = await request.get(buildApiUrl("/health"));
    expect(response.status()).toBe(200);
    const payload = await response.json();
    expect(payload.status).toBe("healthy");
    expect(payload.rbac_enabled).toBe(true);
    expect(payload.deepsearch_receipt_receiver_configured).toBe(true);

    const lastRunAt = payload.reconciler?.last_run_at;
    expect(lastRunAt).toEqual(expect.any(String));

    const lastRunAtMs = Date.parse(lastRunAt);
    expect(Number.isNaN(lastRunAtMs)).toBe(false);

    const reconcilerAgeMs = Date.now() - lastRunAtMs;
    expect(reconcilerAgeMs).toBeGreaterThanOrEqual(-allowedClockSkewMs);
    expect(reconcilerAgeMs).toBeLessThanOrEqual(reconcilerFreshnessLimitMs);
  });
});
