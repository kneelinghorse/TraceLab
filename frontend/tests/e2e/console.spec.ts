import { expect, test } from "@playwright/test";

// Legacy URLs must redirect at the server boundary, retaining the selected ID
// and query rather than keeping a second implementation of the mission pages.
for (const [source, destination] of [
  ["/console", "/admin/observability"],
  ["/console/corrections", "/admin/corrections"],
  ["/console/missions?status=completed", "/missions?status=completed"],
  ["/console/missions/11111111-1111-1111-1111-111111111111", "/missions/11111111-1111-1111-1111-111111111111"],
]) test(`${source} redirects permanently to the canonical page`, async ({ request }) => {
  const response = await request.get(source, { maxRedirects: 0 });
  expect(response.status()).toBe(308);
  expect(response.headers().location).toBe(destination);
});

test("legacy console redirects remain behind admin authorization", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "admin-test", user_id: "member", email: "member@example.test", display_name: "Member" })));
  const requests: string[] = [];
  await page.route("**/api/v1/**", async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (!pathname.endsWith("/auth/me")) requests.push(pathname);
    await route.fulfill({ json: { user_id: "member", email: "member@example.test", display_name: "Member", role: "member" } });
  });
  for (const route of ["/console", "/console/corrections"]) {
    await page.goto(route);
    await expect(page.getByRole("heading", { name: "Admin access required" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Observability", exact: true })).toHaveCount(0);
  }
  expect(requests.filter(p => p.includes("/admin/") || p.includes("/corrections"))).toEqual([]);
});
