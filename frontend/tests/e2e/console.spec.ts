import { expect, test } from "@playwright/test";

// The /console aliases were retired in Sprint 54 (ALIAS-1); route-migration.spec.ts owns
// the 404 assertions, driven by the migration map so it cannot drift from it.
//
// What is unique here is the authorization boundary the aliases used to lead to: their
// successors must still refuse a non-admin, and must not fetch admin data before doing so.
test("the admin successors of the retired console routes stay behind admin authorization", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "admin-test", user_id: "member", email: "member@example.test", display_name: "Member" })));
  const requests: string[] = [];
  await page.route("**/api/v1/**", async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (!pathname.endsWith("/auth/me")) requests.push(pathname);
    await route.fulfill({ json: { user_id: "member", email: "member@example.test", display_name: "Member", role: "member" } });
  });
  for (const route of ["/admin/observability", "/admin/corrections"]) {
    await page.goto(route);
    await expect(page.getByRole("heading", { name: "Admin access required" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Observability", exact: true })).toHaveCount(0);
  }
  // Refusing after fetching would still have leaked the data it was refusing to show.
  expect(requests.filter(p => p.includes("/admin/") || p.includes("/corrections"))).toEqual([]);
});
