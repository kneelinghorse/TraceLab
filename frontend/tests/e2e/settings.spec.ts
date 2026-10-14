import { expect, test } from "@playwright/test";
import path from "node:path";

test.use({ timezoneId: "America/Chicago", locale: "en-US" });

const keyName = "Research workstation — October partner demo and document integrations";

test.beforeEach(async ({ page }) => {
  // At 00:30 in Chicago, the invite's UTC creation time was yesterday locally.
  // Treating these legacy offset-free values as local time also makes key ages negative.
  await page.clock.setFixedTime(new Date("2026-10-13T05:30:00Z"));
  await page.addInitScript(() => localStorage.setItem("tracelab.auth.v2", JSON.stringify({
    token: "settings-fixture", user_id: "settings-user", email: "researcher@example.test", display_name: "Researcher",
  })));
  await page.route("**/api/v1/**", async route => {
    expect(route.request().method()).toBe("GET");
    const pathname = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (pathname.endsWith("/auth/me")) body = { user_id: "settings-user", email: "researcher@example.test", display_name: "Researcher", role: "admin", email_notifications_enabled: true };
    else if (pathname.endsWith("/auth/api-keys")) body = { total: 1, keys: [{ id: "key-1", name: keyName, key_prefix: "fixture", created_at: "2026-10-13T02:30:00", last_used_at: "2026-10-13T04:30:00", expires_at: null }] };
    else if (pathname.endsWith("/auth/invite-codes")) body = { total: 1, codes: [{ id: "invite-1", code: "DEMO2026", status: "unused", created_at: "2026-10-13T03:30:00", used_at: null, expires_at: null }] };
    else if (pathname.endsWith("/spaces")) body = [];
    else if (pathname.endsWith("/activity/summary")) body = { generated_at: "2026-10-13T05:30:00Z", completed_missions_new: 0, new_total: 0, by_type: { mission: 0, report: 0, evidence: 0 } };
    await route.fulfill({ json: body });
  });
});

test("Settings interprets legacy API timestamps as UTC before displaying local times", async ({ page }) => {
  await page.goto("/settings");
  const key = page.locator("li").filter({ hasText: keyName });
  await expect(key).toContainText("Created about 3 hours ago");
  await expect(key).toContainText("Last used about 1 hour ago");
  await expect(page.locator("#invites li")).toContainText("10/12/2026");
  await expect(page.getByRole("button", { name: "Generate code", exact: true })).toBeEnabled();
});

test("member Settings explains how to get an invite without offering an admin-only action", async ({ page }) => {
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: {
    user_id: "settings-user", email: "researcher@example.test", display_name: "Researcher", role: "member", email_notifications_enabled: true,
  } }));
  await page.goto("/settings");
  await expect(page.getByRole("checkbox", { name: "Mission emails" })).toBeChecked();
  await expect(page.getByText("Ask an admin for an invite code.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Generate code", exact: true })).toHaveCount(0);
});

for (const theme of ["light", "dark"] as const) {
  test(`Settings keeps phone action labels readable in ${theme}`, async ({ page }, info) => {
    await page.setViewportSize({ width: 390, height: 1000 });
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/settings");
    await expect(page.getByText(keyName, { exact: true })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    for (const label of [page.getByRole("button", { name: "Revoke", exact: true }), page.getByRole("button", { name: "Copy", exact: true }), page.getByRole("button", { name: "Delete", exact: true }), page.getByText("unused", { exact: true })]) {
      await expect(label).toBeVisible();
      // No per-character wrapping: measure the rendered text, not a CSS class.
      const lines = await label.evaluate(element => {
        const range = document.createRange();
        range.selectNodeContents(element);
        return Array.from(range.getClientRects()).map(rect => ({ left: rect.left, right: rect.right }));
      });
      expect(lines).toHaveLength(1);
      expect(lines[0].left).toBeGreaterThanOrEqual(0);
      expect(lines[0].right).toBeLessThanOrEqual(390);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
    const violations = await page.evaluate(async () => {
      const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
      return (await axe.run(document)).violations.filter(v => ["serious", "critical"].includes(v.impact)).map(v => v.id);
    });
    expect(violations).toEqual([]);
    await page.screenshot({ path: info.outputPath(`settings-${theme}-390.png`), fullPage: true });
  });
}
