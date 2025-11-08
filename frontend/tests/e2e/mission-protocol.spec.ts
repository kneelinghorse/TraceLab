import { expect, test } from "@playwright/test";

import missionDetail from "../fixtures/mission-detail.json";
import missions from "../fixtures/missions.json";
import qualityReport from "../fixtures/quality-report.json";

const missionsApi = "http://localhost:8000/api/v1/missions";
const missionId = "11111111-1111-1111-1111-111111111111";
const endpoints = {
  detail: `${missionsApi}/${missionId}`,
  quality: `http://localhost:8000/api/v1/quality/missions/${missionId}/quality`,
};

const jsonResponse = (payload: unknown) => ({
  status: 200,
  body: JSON.stringify(payload),
  headers: {
    "content-type": "application/json",
  },
});

test.describe("Mission Protocol UI", () => {
  test("renders backlog view and validates new mission workflow", async ({ page }) => {
    await page.route(missionsApi, (route) => route.fulfill(jsonResponse(missions)));

    await page.goto("/missions");

    await expect(page.getByRole("heading", { name: "Mission Protocol Backlog" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "UI Integration + Quality Gates" })).toBeVisible();

    await page.getByRole("button", { name: "Start New Mission" }).click();
    await page.getByRole("button", { name: "Create Mission" }).click();

    await expect(page.getByText("Project ID must be a valid UUID")).toBeVisible();
    await expect(page.getByText("Mission ID is required")).toBeVisible();

    await expect(page.getByRole("link", { name: /View details/i }).first()).toHaveAttribute("href", /missions\//);
  });

  test("renders mission detail view with quality gates", async ({ page }) => {
    await page.route(missionsApi, (route) => route.fulfill(jsonResponse(missions)));
    await page.route(endpoints.detail, (route) => route.fulfill(jsonResponse(missionDetail)));
    await page.route(endpoints.quality, (route) => route.fulfill(jsonResponse(qualityReport)));

    await page.goto(`/missions/${missionId}`);

    await expect(page.getByText("Mission ID: B3.4")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Research Readiness" })).toBeVisible();

    const traceabilityCard = page.getByTestId("gate-traceability");
    await expect(traceabilityCard).toContainText("fail");

    await expect(page.getByRole("button", { name: "Update Mission" })).toBeVisible();
  });
});
