import { expect, test } from "@playwright/test";

const isProductionSmoke = Boolean(process.env.PLAYWRIGHT_BASE_URL);
const apiBase = (process.env.PLAYWRIGHT_API_BASE_URL ?? "https://api.namozine.com").replace(/\/$/, "");
const apiPrefix = (process.env.PLAYWRIGHT_API_PATH_PREFIX ?? "/api/v1").replace(/\/$/, "");
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

  test("API health endpoint stays reachable", async ({ request }) => {
    const response = await request.get(buildApiUrl("/health"));
    expect(response.status()).toBe(200);
    const payload = await response.json();
    expect(payload.status).toBe("healthy");
  });
});
