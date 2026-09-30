import { expect, test } from "@playwright/test";
import path from "node:path";

for (const theme of ["light", "dark"] as const) for (const width of [390, 820, 1440]) {
  test(`admin recovery confirmation ${theme} ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript(() => localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "admin-fixture", user_id: "admin", email: "admin@controlled.org", display_name: "Admin" })));
    const users = [
      { id: "admin", email: "admin@controlled.org", display_name: "Admin", role: "admin", is_active: true, created_at: "2026-01-01T00:00:00Z", last_login_at: null },
      { id: "target", email: "recover@controlled.org", display_name: "Recovery candidate", role: "member", is_active: true, created_at: "2026-01-01T00:00:00Z", last_login_at: null },
      { id: "disabled", email: "disabled@controlled.org", display_name: "Disabled", role: "member", is_active: false, created_at: "2026-01-01T00:00:00Z", last_login_at: null },
    ];
    let sends = 0;
    await page.route("**/api/v1/**", async route => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname.endsWith("/auth/me")) return route.fulfill({ json: { ...users[0], user_id: "admin" } });
      if (pathname.endsWith("/admin/users")) return route.fulfill({ json: users });
      if (pathname.endsWith("/admin/users/target/password-reset")) {
        sends++;
        expect(route.request().method()).toBe("POST");
        expect(route.request().postDataJSON()).toEqual({});
        if (sends === 1) return route.fulfill({ status: 503, json: { detail: "The reset email could not be sent. Please try again later." } });
        return route.fulfill({ json: { delivery_status: "accepted", message: "The email provider accepted the reset email. Ask the recipient to check their inbox and spam folder." } });
      }
      return route.fulfill({ json: {} });
    });
    await page.goto("/admin/users");
    const row = page.getByRole("row").filter({ hasText: "recover@controlled.org" });
    const trigger = row.getByRole("button", { name: "Send password reset link" });
    await expect(trigger).toBeVisible();
    await expect(page.getByRole("row").filter({ hasText: "disabled@controlled.org" }).getByRole("button", { name: "Send password reset link" })).toBeDisabled();
    await trigger.focus();
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "Send password reset link?" });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("Recovery candidate");
    await expect(dialog).toContainText("recover@controlled.org");
    expect(sends).toBe(0);
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Send reset email" }).focus();
    await page.keyboard.press("Tab");
    await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
    await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
    const audit = await page.evaluate(async () => {
      const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
      return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["serious", "critical"].includes(v.impact)) };
    });
    if (audit.overflow) {
      console.log(await page.evaluate(() => Array.from(document.querySelectorAll("body *"))
        .filter(element => element.getBoundingClientRect().right > innerWidth)
        .map(element => ({ tag: element.tagName, classes: element.className, width: element.getBoundingClientRect().width, overflow: getComputedStyle(element).overflowX })).slice(0, 12)));
    }
    expect(audit).toEqual({ overflow: false, violations: [] });
    await page.screenshot({ path: info.outputPath(`admin-recovery-${theme}-${width}.png`), fullPage: true });
    await page.keyboard.press("Tab");
    await page.keyboard.press("Enter");
    await expect(dialog.getByRole("alert")).toContainText("could not be sent");
    await dialog.getByRole("button", { name: "Send reset email" }).click();
    await expect(dialog).not.toBeVisible();
    await expect(page.getByRole("status")).toContainText("provider accepted");
    expect(sends).toBe(2);
    await expect(row).toContainText("Active");
  });
}
