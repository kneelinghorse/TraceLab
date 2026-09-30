import { expect, test } from "@playwright/test";
import path from "node:path";

for (const theme of ["light", "dark"] as const) for (const width of [390, 820, 1440]) {
  test(`password recovery ${theme} ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript(() => localStorage.clear());
    const requests: { path: string; body: unknown }[] = [];
    const token = "local-fixture-".padEnd(43, "x");
    await page.route("**/api/v1/**", async route => {
      const request = route.request();
      const endpoint = new URL(request.url()).pathname;
      expect(request.url()).not.toContain(token);
      expect(request.headers().referer ?? "").not.toContain(token);
      if (endpoint.includes("password-reset")) {
        expect(request.headers().authorization).toBeUndefined();
        requests.push({ path: endpoint, body: request.postDataJSON() });
        await route.fulfill({ status: endpoint.endsWith("request") ? 202 : 200, json: { message: endpoint.endsWith("request") ? "If eligible, instructions will be sent." : "Password changed. Sign in with your new password." } });
      } else await route.fulfill({ json: { user_id: "other", role: "member" } });
    });
    await page.goto("/");
    await page.getByRole("link", { name: "Forgot password?" }).click();
    await expect(page.getByRole("heading", { name: "Forgot password?" })).toBeVisible();
    await page.getByLabel("Email", { exact: true }).fill("local@controlled.org");
    await page.getByRole("button", { name: "Send reset link" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("status")).toContainText("If eligible");
    // Opening a link never sends a confirm request, including in another user's session.
    await page.addInitScript(() => localStorage.setItem("tracelab.auth.v2", JSON.stringify({ token: "other-fixture", user_id: "other", email: "other@controlled.org" })));
    await page.goto(`/reset-password#token=${token}`);
    await expect(page.getByLabel("New password", { exact: true })).toBeVisible();
    expect(page.url()).toMatch(/\/reset-password$/);
    expect(requests).toHaveLength(1);
    expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain(token);
    await page.addScriptTag({ path: path.resolve("node_modules/axe-core/axe.min.js") });
    const audit = await page.evaluate(async () => {
      const axe = (window as unknown as { axe: { run: (node: Document) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe;
      return { overflow: document.documentElement.scrollWidth > innerWidth, violations: (await axe.run(document)).violations.filter(v => ["serious", "critical"].includes(v.impact)) };
    });
    expect(audit).toEqual({ overflow: false, violations: [] });
    await page.screenshot({ path: info.outputPath(`recovery-${theme}-${width}.png`), fullPage: true });
    await page.getByLabel("New password", { exact: true }).fill("local-fixture-password");
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Confirm new password")).toBeFocused();
    await page.getByLabel("Confirm new password").fill("local-fixture-password");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Save new password" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("status")).toContainText("Password changed");
    expect(requests).toHaveLength(2);
    expect(await page.evaluate(() => localStorage.getItem("tracelab.auth.v2"))).toBeNull();
    await page.getByRole("link", { name: "Back to sign in" }).click();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });
}
