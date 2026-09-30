import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
import { MissionRunActivity } from "@/components/missions/MissionRunActivity";
import type { ApiMission, MissionStatus } from "@/types/mission";
const mocks = vi.hoisted(() => ({ get: vi.fn(), userId: "reader" as string | undefined }));
vi.mock("@/lib/api/http", () => ({ httpClient: mocks }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: mocks.userId ? { user_id: mocks.userId } : null }) }));
function run(status: MissionStatus, metadata: Record<string, unknown> = {}) {
  const mission = { id: "run-1", status, execution_metadata: metadata } as ApiMission;
  render(<SWRConfig value={{ provider: () => new Map(), shouldRetryOnError: false }}><MissionRunActivity mission={mission} /></SWRConfig>);
}
beforeEach(() => { mocks.userId = "reader"; mocks.get.mockReset().mockResolvedValue([]); });
it.each(["draft", "queued", "in_progress", "completed", "blocked", "cancelled", "validation_failed"] as MissionStatus[])("keeps missing observations unknown for %s and never calls empty logs live", async status => {
  run(status, { current_loop: 2, sources: 99, coverage: 0.9 });
  expect(await screen.findByText(status === "queued" || status === "in_progress" ? /Waiting for the first/ : /No runner observations/)).toBeVisible();
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

afterEach(() => { cleanup(); vi.useRealTimers(); });
const line = (message = JSON.stringify({ phase: "running", event: "phase_started", count: 3 }), attempt = 1) => ({
  id: `log-${attempt}`, message, level: "INFO", attempt_count: attempt,
  logged_at: new Date(Date.now() - 1000).toISOString(), created_at: new Date().toISOString(),
});
it("renders known observations, attempt boundaries, and readable unknown text without invented progress", async () => {
  mocks.get.mockImplementation(async path => path.endsWith("/logs") ? [line(), line("Future worker event: investigating sources", 2)] : []);
  run("in_progress");
  expect(await screen.findByText(/Researching · Started · count: 3/)).toBeVisible();
  expect(screen.getByText(/Future worker event/)).toBeVisible();
  expect(screen.getByText("Attempt 1")).toBeVisible();
  expect(screen.getByText("Attempt 2")).toBeVisible();
  expect(screen.getByText("Receiving runner observations.")).toBeVisible();
  expect(screen.queryByRole("progressbar")).toBeNull();
});
it("uses receiver time for quiet gaps and retains observations during a transient outage", async () => {
  mocks.get.mockImplementation(async path => path.endsWith("/logs") ? [{ ...line("Retain this observation"), created_at: new Date(Date.now() - 35000).toISOString() }] : []);
  run("in_progress");
  expect(await screen.findByText(/may be working quietly/)).toBeVisible();
  mocks.get.mockRejectedValue(new Error("offline"));
  fireEvent.click(screen.getByRole("button", { name: "Refresh logs" }));
  expect(await screen.findByText(/Log refresh failed/)).toBeVisible();
  expect(screen.getByText(/Retain this observation/)).toBeVisible();
});
it.each([401, 403, 404])("hides cached observations after access returns %s", async status => {
  mocks.get.mockImplementation(async path => path.endsWith("/logs") ? [line("Private retained observation")] : []);
  run("in_progress");
  expect(await screen.findByText(/Private retained/)).toBeVisible();
  mocks.get.mockRejectedValue(Object.assign(new Error("denied"), { status }));
  fireEvent.click(screen.getByRole("button", { name: "Refresh logs" }));
  expect(await screen.findByText(/unavailable for this account/)).toBeVisible();
  expect(screen.queryByText(/Private retained/)).toBeNull();
});
it("isolates mission and user changes even when the old request resolves late", async () => {
  let resolveOld!: (rows: unknown[]) => void;
  mocks.get.mockImplementation(path => path === "/missions/old/logs" ? new Promise(resolve => { resolveOld = resolve; }) : Promise.resolve([]));
  const cache = new Map();
  const view = (id: string) => <SWRConfig value={{ provider: () => cache, shouldRetryOnError: false }}><MissionRunActivity mission={{ id, status: "in_progress" } as ApiMission} /></SWRConfig>;
  const { rerender } = render(view("old"));
  await waitFor(() => expect(resolveOld).toBeDefined());
  rerender(view("new"));
  await act(async () => resolveOld([line("Old private observation")]));
  expect(screen.queryByText(/Old private/)).toBeNull();
  mocks.userId = "another-reader";
  rerender(view("old"));
  expect(screen.queryByText(/Old private/)).toBeNull();
  mocks.userId = undefined;
  rerender(view("old"));
  expect(screen.getByText(/unavailable for this account/)).toBeVisible();
});
it("revalidates late terminal flushes for a bounded window and retains manual refresh", async () => {
  vi.useFakeTimers();
  let reads = 0;
  mocks.get.mockImplementation(async path => path.endsWith("/logs") ? (++reads > 1 ? [line("Final observation")] : []) : []);
  await act(async () => run("completed"));
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  expect(screen.getByText(/Final observation/)).toBeVisible();
  await act(async () => { await vi.advanceTimersByTimeAsync(45000); });
  const stoppedAt = reads;
  await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
  expect(reads).toBe(stoppedAt);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Refresh logs" })));
  expect(reads).toBe(stoppedAt + 1);
  expect(screen.getByText("Retained observations from this run.")).toBeVisible();
});
