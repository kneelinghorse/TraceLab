import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { SWRConfig } from "swr";
import type { HomeSnapshot } from "@/lib/api/home";
import type { ActivityItem } from "@/lib/api/activity";

const mocks = vi.hoisted(() => ({ get: vi.fn(), list: vi.fn(), markViewed: vi.fn(), summary: vi.fn() }));
vi.mock("@/lib/api/home", () => ({ homeApi: { get: mocks.get } }));
vi.mock("@/lib/api/activity", async original => ({ ...await original<object>(), activityApi: { list: mocks.list, markViewed: mocks.markViewed, summary: mocks.summary } }));
vi.mock("@/components/AuthGate", () => ({ AuthGate: ({ children }: { children: ReactNode }) => children }));
vi.mock("@/components/Navigation", () => ({ NavigationIcon: () => null }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { user_id: "reader" } }) }));
vi.mock("next/head", () => ({ default: () => null }));

import HomePage from "@/pages/index";
import { OPEN_COMMAND_PALETTE_EVENT } from "@/lib/command-palette";

const failure: ActivityItem = { type: "mission", id: "mission-1", title: "Old failed research", subtitle: "RESEARCH-1", status: "validation_failed", occurred_at: "2026-08-20T02:00:00", href: "/missions/mission-1", new: true };
const report: ActivityItem = { type: "report", id: "report-1", title: "Fresh report", subtitle: null, status: "draft", occurred_at: "2026-09-13T02:00:00", href: "/reports/report-1", new: true };
const evidence: ActivityItem = { type: "evidence", id: "evidence-1", title: "12 evidence entries · DeepSearch", subtitle: "worker-run", status: null, occurred_at: "2026-09-12T02:00:00", href: "/evidence?project_id=p", new: false };

function snapshot(): HomeSnapshot {
  const running = {
    id: "mission-2", mission_id: "RESEARCH-2", title: "Research in progress", status: "in_progress",
    updated_at: "2026-09-13T02:00:00", started_at: null, completed_at: null,
    progress: { phase: null, percent: null, current_step: null, total_steps: null },
    report_id: null, evidence_count: 0, evidence_href: null,
  };
  return {
    generated_at: "2026-09-13T02:01:00", refresh_seconds: 30,
    missions: { total: 433, by_status: { completed: 401 } },
    activity: { generated_at: "2026-09-13T02:01:00", refresh_seconds: 30, page: 1, page_size: 10, total: 12, new_total: 2, items: [report, evidence, failure] },
    active_runs: { total: 1, items: [running] },
    recent_reports: { total: 201, items: [{ id: "report-1", title: "Research report", href: "/reports/report-1", updated_at: report.occurred_at }] },
    recent_projects: { total: 0, items: [] }, favorites: { total: 0, items: [] }, evidence_activity: { total: 0, items: [] },
  };
}
function home() {
  return render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}><HomePage /></SWRConfig>);
}
beforeEach(() => { mocks.get.mockReset(); mocks.list.mockReset(); mocks.markViewed.mockReset(); mocks.summary.mockReset(); });

describe("Home's recent activity", () => {
  it("lists what happened newest first with status as a label only, and keeps missing progress unknown", async () => {
    mocks.get.mockResolvedValue(snapshot());
    home();
    expect(await screen.findByRole("link", { name: "433 missions" })).toHaveAttribute("href", "/missions");
    const region = screen.getByRole("region", { name: "Recent activity" });
    expect(within(region).getByText("12")).toBeVisible();
    expect(within(region).getByText("Newest first. 2 new since you last looked.")).toBeVisible();
    const rows = within(region).getAllByRole("listitem");
    expect(rows.map(row => within(row).getByRole("link").textContent)).toEqual(["Fresh report", "12 evidence entries · DeepSearch", "Old failed research"]);
    expect(within(rows[2]).getByText(/validation.failed/i)).toBeVisible();
    expect(within(rows[2]).getByRole("button", { name: "Mark viewed" })).toBeVisible();
    expect(within(rows[1]).queryByRole("button", { name: "Mark viewed" })).toBeNull();
    expect(screen.queryByText(/Needs attention|Mark reviewed|dashboards/i)).toBeNull();
    expect(screen.getByText("Progress not reported yet.")).toBeVisible();
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.getByRole("link", { name: "Inspect run" })).toHaveAttribute("href", "/missions/mission-2");
    expect(screen.getByRole("link", { name: "All running" })).toHaveAttribute("href", "/missions?status=in_progress");
  });

  it("keeps loading, empty and error states distinct and supports retry", async () => {
    mocks.get.mockRejectedValueOnce(new Error("offline"));
    const data = snapshot();
    data.missions = { total: 0, by_status: { completed: 0 } };
    data.activity = { ...data.activity, total: 0, new_total: 0, items: [] };
    data.active_runs = { total: 0, items: [] };
    mocks.get.mockResolvedValueOnce(data);
    home();
    expect(screen.getByRole("status")).toHaveTextContent("Loading your workspace");
    expect(await screen.findByRole("alert")).toHaveTextContent("Home could not load");
    expect(screen.queryByText("Nothing has happened yet.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Nothing has happened yet.")).toBeVisible();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("marks an item viewed explicitly or by opening it, then refreshes from the server", async () => {
    const initial = snapshot();
    mocks.get.mockResolvedValue(initial);
    mocks.markViewed.mockResolvedValue({ viewed: 1, new_total: 1 });
    home();
    const region = await screen.findByRole("region", { name: "Recent activity" });
    const viewedSnapshot = { ...initial, activity: { ...initial.activity, new_total: 1, items: [{ ...report, new: false }, evidence, failure] } };
    mocks.get.mockResolvedValue(viewedSnapshot);
    fireEvent.click(within(region).getAllByRole("button", { name: "Mark viewed" })[0]);
    await waitFor(() => expect(mocks.markViewed).toHaveBeenCalledWith([{ type: "report", id: "report-1", occurred_at: report.occurred_at }]));
    expect(await within(region).findByText("Newest first. 1 new since you last looked.")).toBeVisible();
    fireEvent.click(within(region).getByRole("link", { name: "Old failed research" }));
    await waitFor(() => expect(mocks.markViewed).toHaveBeenLastCalledWith([{ type: "mission", id: "mission-1", occurred_at: failure.occurred_at }]));
  });

  it("loads more activity on demand and retains stale data when refresh fails", async () => {
    const data = snapshot();
    mocks.get.mockResolvedValueOnce(data);
    mocks.list.mockResolvedValueOnce({ ...data.activity, page: 2, items: [{ ...evidence, id: "evidence-2", title: "3 evidence entries · Research agent" }] });
    home();
    await screen.findByRole("link", { name: "433 missions" });
    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(await screen.findByText("3 evidence entries · Research agent")).toBeVisible();
    expect(mocks.list).toHaveBeenCalledWith({ page: 2, page_size: 10 });
    mocks.get.mockRejectedValueOnce(new Error("offline"));
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh" })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("last successful snapshot");
    expect(screen.getByText("Old failed research")).toBeVisible();
  });

  it("opens the shared command palette from Home", async () => {
    mocks.get.mockResolvedValue(snapshot());
    const open = vi.fn();
    window.addEventListener(OPEN_COMMAND_PALETTE_EVENT, open);
    home();
    fireEvent.click(screen.getByRole("button", { name: /Search research or jump to a section/ }));
    expect(open).toHaveBeenCalledOnce();
    window.removeEventListener(OPEN_COMMAND_PALETTE_EVENT, open);
    await screen.findByRole("link", { name: "433 missions" });
  });
});
import "@testing-library/jest-dom/vitest";
