import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { SWRConfig } from "swr";
import type { HomeSnapshot } from "@/lib/api/home";

const mocks = vi.hoisted(() => ({ get: vi.fn(), review: vi.fn() }));
vi.mock("@/lib/api/home", () => ({ homeApi: mocks }));
vi.mock("@/components/AuthGate", () => ({ AuthGate: ({ children }: { children: ReactNode }) => children }));
vi.mock("@/components/Navigation", () => ({ NavigationIcon: () => null }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { user_id: "reader" } }) }));
vi.mock("next/head", () => ({ default: () => null }));

import HomePage from "@/pages/index";
import { OPEN_COMMAND_PALETTE_EVENT } from "@/lib/command-palette";

function snapshot(): HomeSnapshot {
  const item = {
    id: "mission-1", mission_id: "RESEARCH-1", title: "Evidence for review", status: "completed",
    updated_at: "2026-09-13T02:00:00", started_at: null, completed_at: "2026-09-13T02:00:00",
    reason: "unreviewed" as const, progress: { phase: null, percent: null, current_step: null, total_steps: null },
    report_id: "report-1", evidence_count: 50, evidence_href: "/evidence?project_id=p&mission_id=mission-1",
  };
  return {
    generated_at: "2026-09-13T02:01:00", refresh_seconds: 30, stalled_after_seconds: 3600,
    missions: { total: 433, by_status: { completed: 401 } }, attention: { total: 32, items: [item] },
    active_runs: { total: 1, items: [{ ...item, id: "mission-2", title: "Research in progress", status: "in_progress", reason: null }] },
    recent_reports: { total: 201, items: [{ id: "report-1", title: "Research report", href: "/reports/report-1", updated_at: item.updated_at }] },
    recent_projects: { total: 0, items: [] }, favorites: { total: 0, items: [] }, evidence_activity: { total: 0, items: [] },
  };
}
function home() {
  return render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}><HomePage /></SWRConfig>);
}
beforeEach(() => { mocks.get.mockReset(); mocks.review.mockReset(); });

describe("Home's operator workflow", () => {
  it("shows server totals and result links, and keeps missing progress unknown", async () => {
    mocks.get.mockResolvedValue(snapshot());
    home();
    expect(await screen.findByRole("link", { name: "433 missions" })).toHaveAttribute("href", "/missions");
    expect(within(screen.getByRole("region", { name: "Needs attention" })).getByText("32")).toBeVisible();
    expect(screen.getByRole("link", { name: "Open report" })).toHaveAttribute("href", "/reports/report-1");
    expect(screen.getByRole("link", { name: "Evidence (50)" })).toHaveAttribute("href", "/evidence?project_id=p&mission_id=mission-1");
    expect(screen.getByRole("link", { name: "At risk missions" })).toHaveAttribute("href", "/missions?view=attention&reason=validation_failed&reason=blocked&reason=stalled");
    expect(screen.getByRole("link", { name: "Unreviewed completions" })).toHaveAttribute("href", "/missions?view=attention&reason=unreviewed");
    expect(screen.getByText("Progress not reported yet.")).toBeVisible();
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.getByRole("link", { name: "Inspect run" })).toHaveAttribute("href", "/missions/mission-2");
  });

  it("keeps loading, empty and error states distinct and supports retry", async () => {
    mocks.get.mockRejectedValueOnce(new Error("offline"));
    const data = snapshot();
    data.missions = { total: 0, by_status: { completed: 0 } };
    data.attention = { total: 0, items: [] };
    data.active_runs = { total: 0, items: [] };
    mocks.get.mockResolvedValueOnce(data);
    home();
    expect(screen.getByRole("status")).toHaveTextContent("Loading your workspace");
    expect(await screen.findByRole("alert")).toHaveTextContent("Home could not load");
    expect(screen.queryByText("You’re up to date.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("You’re up to date.")).toBeVisible();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("reviews explicitly and refreshes from the server; failed reviews remain visible", async () => {
    const initial = snapshot();
    mocks.get.mockResolvedValue(initial);
    mocks.review.mockRejectedValueOnce(new Error("changed"));
    home();
    fireEvent.click(await screen.findByRole("button", { name: "Mark reviewed" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Review could not be saved");
    expect(screen.getByRole("link", { name: "Evidence for review" })).toBeVisible();
    mocks.review.mockResolvedValueOnce(undefined);
    mocks.get.mockResolvedValueOnce({ ...initial, attention: { total: 0, items: [] } });
    fireEvent.click(screen.getByRole("button", { name: "Mark reviewed" }));
    expect(await screen.findByText("You’re up to date.")).toBeVisible();
    expect(mocks.review).toHaveBeenLastCalledWith(initial.attention.items[0]);
  });

  it("refreshes changed attention and retains stale data when refresh fails", async () => {
    const data = snapshot();
    mocks.get.mockResolvedValueOnce(data);
    home();
    await screen.findByRole("link", { name: "433 missions" });
    mocks.get.mockResolvedValueOnce({ ...data, attention: { total: 1, items: [{ ...data.attention.items[0], title: "Validation needs attention", status: "validation_failed", reason: "validation_failed" }] } });
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText("Validation needs attention")).toBeVisible();
    mocks.get.mockRejectedValueOnce(new Error("offline"));
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh" })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("last successful snapshot");
    expect(screen.getByText("Validation needs attention")).toBeVisible();
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
