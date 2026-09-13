import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
import type { ReactNode } from "react";
const mocks = vi.hoisted(() => ({ get: vi.fn(), status: vi.fn(), telemetry: vi.fn(), deadLetter: vi.fn(), trigger: vi.fn(), process: vi.fn(), clear: vi.fn(), role: { role: "admin", status: "ready", refetch: vi.fn() } }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isReady: true, isAuthenticated: true, user: { user_id: "admin" } }) }));
vi.mock("@/contexts/RoleContext", async original => ({ ...await original<typeof import("@/contexts/RoleContext")>(), useRole: () => mocks.role }));
vi.mock("@/lib/api/admin-stats", () => ({ adminStatsApi: { get: mocks.get } }));
vi.mock("@/lib/api/console", () => ({ getCorrectionStatus: mocks.status, getCorrectionTelemetry: mocks.telemetry, getDeadLetterQueue: mocks.deadLetter, triggerCorrections: mocks.trigger, processCorrections: mocks.process, clearCompletedCorrections: mocks.clear }));
import ObservabilityPage from "@/pages/admin/observability";
import CorrectionsPage from "@/pages/admin/corrections";
const stats = () => ({ generated_at: "2026-09-13T12:00:00Z", refresh_seconds: 30, scope: "system", missions: { total: 433, by_status: { completed: 412, draft: 21 } }, projects: 51, documents: 127, chunks: 9000, reports: 481, ingestion_jobs: { total: 101, by_status: { COMPLETED: 101 } }, graph_edges: 2345, graph_edges_by_type: { references: 2345 }, evidence_entries: 370, evidence_sources: 52, evidence_notes: 4, recent_missions: [{ id: "one", mission_id: "DS-1", title: "Recent research", status: "completed", updated_at: "2026-09-13T11:00:00Z" }], worker: { status: "unavailable", checked_at: "2026-09-13T12:00:00Z", missions_completed: null, error: "Worker health check timed out" }, reconciler: { last_run_at: null, runs: 0 }, corrections: null, corrections_error: "Queue unavailable", process_scope: "This API process resets on restart." });
beforeEach(() => {
  vi.clearAllMocks(); mocks.role.role = "admin";
  mocks.get.mockReset().mockResolvedValue(stats());
  mocks.status.mockResolvedValue({ stats: { total: 125, pending: 123, completed: 2, failed: 0, in_progress: 0, skipped: 0 }, error_distribution: {}, recent_items: [], last_updated: "2026-09-13T12:00:00Z" });
  mocks.telemetry.mockResolvedValue({ success_rate: 1, queue_counts: {}, last_updated: "2026-09-13T12:00:00Z" });
  mocks.deadLetter.mockResolvedValue({ count: 100, items: [{ url: "https://example.test/hook", error: "Unavailable", attempts: 5, payload: { mission_id: "one" }, last_attempt: "2026-09-13T12:00:00Z" }] });
  mocks.trigger.mockReset().mockResolvedValue({ triggered: 2, message: "2 corrections triggered" });
  mocks.process.mockReset().mockResolvedValue({ processed: 2, message: "2 corrections processed" });
  mocks.clear.mockReset().mockResolvedValue({ cleared: 2, message: "2 completed corrections cleared" });
});
async function browser(component: ReactNode) { await act(async () => { render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}>{component}</SWRConfig>); }); }
describe("admin observability", () => {
  it("renders server totals separately from recent rows and preserves unknown telemetry", async () => {
    await browser(<ObservabilityPage />);
    expect(await screen.findByText("433")).toBeVisible();
    expect(screen.getByText("Showing 1 of 433 missions.")).toBeVisible();
    expect(within(screen.getByRole("region", { name: "Mission statuses" })).getByText("412")).toBeVisible();
    const worker = within(screen.getByRole("region", { name: "DeepSearch worker" }));
    expect(worker.getByText("unavailable")).toBeVisible();
    expect(worker.getAllByText("Not reported")).toHaveLength(5);
    expect(screen.getByText("Queue unavailable")).toBeVisible();
    expect(screen.getByRole("link", { name: "Recent research" })).toHaveAttribute("href", "/missions/one");
    mocks.get.mockResolvedValue({ ...stats(), missions: { total: 434, by_status: { completed: 413, draft: 21 } } });
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText("434")).toBeVisible();
  });
  it("retries failed reads without presenting an empty system", async () => {
    mocks.get.mockRejectedValueOnce(new Error("Unavailable"));
    await browser(<ObservabilityPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("could not load");
    expect(screen.queryByText("Missions")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("433")).toBeVisible();
  });
  it.each(["member", "service"])("never requests system aggregates or correction data for %s", async role => {
    mocks.role.role = role;
    await browser(<><ObservabilityPage /><CorrectionsPage /></>);
    expect(screen.getAllByText("Admin access required")).toHaveLength(2);
    expect(mocks.get).not.toHaveBeenCalled(); expect(mocks.status).not.toHaveBeenCalled();
  });
  it("preserves correction actions at the new route and exposes total dead letters without a fake clear action", async () => {
    await browser(<CorrectionsPage />);
    expect(await screen.findByRole("button", { name: "Retry Pending" })).toBeVisible();
    expect(mocks.trigger).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Retry Pending" }));
    expect(await screen.findByText("2 corrections triggered")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Process Now" }));
    expect(await screen.findByText("2 corrections processed")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Clear Completed" }));
    expect(await screen.findByText("2 completed corrections cleared")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /Dead Letter/ }));
    expect(screen.getByText("Dead Letter Queue (100)")).toBeVisible();
    expect(screen.getByText("Showing 1 of 100 failed deliveries.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Clear All" })).toBeNull();
    fireEvent.click(screen.getByText("View Payload"));
    expect(screen.getByText(/"mission_id": "one"/)).toBeVisible();
  });
  it("retains a correction failure until a successful explicit retry", async () => {
    mocks.process.mockRejectedValueOnce(new Error("Processing unavailable"));
    await browser(<CorrectionsPage />);
    await screen.findByRole("button", { name: "Retry Pending" });
    fireEvent.click(screen.getByRole("button", { name: "Process Now" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Processing unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Process Now" }));
    expect(await screen.findByText("2 corrections processed")).toBeVisible();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
