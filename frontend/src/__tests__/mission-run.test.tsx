import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
import { MissionRunActivity } from "@/components/missions/MissionRunActivity";
import type { ApiMission, MissionStatus } from "@/types/mission";
const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/http", () => ({ httpClient: mocks }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { user_id: "reader" } }) }));
function run(status: MissionStatus, metadata: Record<string, unknown> = {}) {
  const mission = { id: "run-1", status, execution_metadata: metadata } as ApiMission;
  render(<SWRConfig value={{ provider: () => new Map(), shouldRetryOnError: false }}><MissionRunActivity mission={mission} /></SWRConfig>);
}
beforeEach(() => { mocks.get.mockReset().mockResolvedValue([]); });
it.each(["draft", "queued", "in_progress", "completed", "blocked", "cancelled", "validation_failed"] as MissionStatus[])("keeps missing observations unknown for %s and never calls empty logs live", async status => {
  run(status, { current_loop: 2, sources: 99, coverage: 0.9 });
  expect(await screen.findByText(/Logs unavailable/)).toBeVisible();
  expect(screen.getByText("Phase unknown")).toBeVisible();
  expect(screen.getByText("Step progress unknown")).toBeVisible();
  expect(screen.queryByText("Live")).toBeNull();
  expect(screen.queryByRole("progressbar")).toBeNull();
  expect(screen.getByText(/No recent activity/)).toBeVisible();
  expect(mocks.get).toHaveBeenCalledWith("/missions/events/recent", { params: { mission_id: "run-1", limit: 50 } });
});
it("displays only observed phase and valid steps, with recent event details", async () => {
  mocks.get.mockImplementation(async path => path.endsWith("recent") ? [{ event_type: "mission.started", timestamp: "2026-09-13T00:00:00Z", mission_id: "run-1", status: "in_progress" }] : []);
  run("in_progress", { current_phase: "synthesis", current_step: 3, total_steps: 5, progress_percent: 60 });
  expect(screen.getByText("synthesis")).toBeVisible();
  expect(screen.getByText("Step 3 of 5")).toBeVisible();
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "60");
  expect(await screen.findByText("Mission started")).toBeVisible();
});
it("rejects invalid step pairs and distinguishes failed event reads from an empty history", async () => {
  mocks.get.mockRejectedValue(new Error("offline"));
  run("in_progress", { current_phase: [], current_step: 8, total_steps: 2, progress_percent: 101 });
  expect(await screen.findByText(/Recent activity unavailable/)).toBeVisible();
  expect(screen.queryByText(/No recent activity/)).toBeNull();
  expect(screen.getByText("Step progress unknown")).toBeVisible();
  expect(screen.queryByRole("progressbar")).toBeNull();
});
