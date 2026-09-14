import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
const mocks = vi.hoisted(() => ({ attention: vi.fn(), list: vi.fn(), create: vi.fn(), rename: vi.fn(), delete: vi.fn() }));
vi.mock("@/lib/api/home", () => ({ homeApi: { attention: mocks.attention } }));
vi.mock("@/lib/api/missionViews", async original => ({ ...await original<object>(), missionViewsApi: mocks }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { user_id: "reader" } }) }));
import { MissionDashboards } from "@/components/missions/MissionDashboards";
import { missionViewHref } from "@/lib/api/missionViews";
import { HttpError, buildApiUrl } from "@/lib/api/http";
const filters = { view: "attention" as const, reason: ["blocked", "stalled"], project_id: "p", status: "blocked" as const };
const saved = { id: "saved-1", name: "Review Space", filters, total: 118, entity_type: "missions", created_at: "2026-09-14T00:00:00", updated_at: "2026-09-14T00:00:00" };
function mount() { return render(<SWRConfig value={{ provider: () => new Map(), shouldRetryOnError: false, dedupingInterval: 0 }}><MissionDashboards filters={filters} /></SWRConfig>); }
beforeEach(() => {
  vi.resetAllMocks();
  mocks.attention.mockResolvedValue({ generated_at: "2026-09-14T00:00:00", total: 243, dashboards: [{ key: "at_risk", total: 123 }, { key: "unreviewed", total: 120 }] });
  mocks.list.mockResolvedValue({ items: [saved] });
});
it("uses independent server totals and reconstructs every repeated reason without saving pagination", async () => {
  mount();
  expect(await screen.findByRole("link", { name: "At risk missions 123" })).toHaveAttribute("href", "/missions?view=attention&reason=validation_failed&reason=blocked&reason=stalled");
  expect(screen.getByRole("link", { name: "Unreviewed completions 120" })).toHaveAttribute("href", "/missions?view=attention&reason=unreviewed");
  expect(await screen.findByRole("link", { name: "Review Space (118)" })).toHaveAttribute("href", missionViewHref(filters));
  expect(new URL(buildApiUrl("/missions", { view: "attention", reason: filters.reason })).searchParams.getAll("reason")).toEqual(filters.reason);
  fireEvent.click(screen.getByRole("button", { name: "Save view" }));
  fireEvent.change(screen.getByLabelText("View name"), { target: { value: "  My exceptions  " } });
  fireEvent.click(screen.getByRole("button", { name: "Save", exact: true }));
  await waitFor(() => expect(mocks.create).toHaveBeenCalledWith("My exceptions", filters));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});
it("renames and deletes only the selected view with explicit dialogs and refreshed counts", async () => {
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "Rename Review Space" }));
  expect(mocks.rename).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("View name"), { target: { value: "Reviewed research" } });
  mocks.list.mockResolvedValue({ items: [{ ...saved, name: "Reviewed research", total: 3 }] });
  fireEvent.click(screen.getByRole("button", { name: "Save", exact: true }));
  await waitFor(() => expect(mocks.rename).toHaveBeenCalledWith(saved.id, "Reviewed research"));
  expect(await screen.findByRole("link", { name: "Reviewed research (3)" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Delete Reviewed research" }));
  expect(mocks.delete).not.toHaveBeenCalled();
  mocks.list.mockResolvedValue({ items: [] });
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete view" }));
  await waitFor(() => expect(mocks.delete).toHaveBeenCalledWith(saved.id));
  expect(await screen.findByText("No saved views yet.")).toBeVisible();
});
it("distinguishes missing views from conflicts and keeps the dialog available for correction", async () => {
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "Rename Review Space" }));
  mocks.rename.mockRejectedValueOnce(new HttpError("Missing", 404));
  fireEvent.click(screen.getByRole("button", { name: "Save", exact: true }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Saved view not found");
  mocks.rename.mockRejectedValueOnce(new HttpError("A saved view with that name already exists.", 409));
  fireEvent.click(screen.getByRole("button", { name: "Save", exact: true }));
  expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
  expect(screen.getByRole("dialog")).toBeVisible();
});
it("keeps loading and failed dashboards distinct from a successful empty saved list", async () => {
  mocks.attention.mockRejectedValueOnce(new Error("offline"));
  mocks.list.mockResolvedValue({ items: [] });
  mount();
  expect(screen.getByText("Loading dashboards…")).toBeVisible();
  expect(await screen.findByRole("alert")).toHaveTextContent("Dashboard totals unavailable");
  expect(screen.queryByRole("link", { name: /At risk missions/ })).toBeNull();
  expect(screen.getByText("No saved views yet.")).toBeVisible();
});
