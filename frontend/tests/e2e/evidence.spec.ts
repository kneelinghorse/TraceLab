import { expect, test } from "@playwright/test";

for (const theme of ["light", "dark"] as const) for (const width of [390, 1440]) {
  test(`evidence promotion traps keyboard focus and cancels without writing in ${theme} at ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript(({ theme }) => {
      localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "fixture", user_id: "reader", email: "reader@example.test" }));
      localStorage.setItem("tracelab.theme.v1:reader", theme);
    }, { theme });
    let writes = 0;
    await page.route("**/api/v1/**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (route.request().method() !== "GET") writes++;
      const body = path.endsWith("/auth/me") ? { user_id: "reader", email: "reader@example.test", role: "member" }
        : path.endsWith("/projects") ? { data: [{ id: "project", name: "Research" }], pagination: { pages: 1 } }
        : { entries: [], notes: [], entry_total: 0, note_total: 0, page: 1, page_size: 20 };
      await route.fulfill({ json: body });
    });
    await page.goto("/evidence?project_id=project&session_key=research-session");
    const trigger = page.getByRole("button", { name: "Promote session" });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "Promote evidence session" });
    await expect(dialog).toBeVisible();
    for (const key of ["Tab", "Shift+Tab"]) for (let count = 0; count < 8; count++) {
      await page.keyboard.press(key);
      expect(await dialog.evaluate(node => node.contains(document.activeElement))).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();
    expect(writes).toBe(0);
  });
}
