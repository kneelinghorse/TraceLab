import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
import type { ApiMission, MissionStatus } from "@/types/mission";
const mocks = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn(), update: vi.fn(), review: vi.fn(), home: vi.fn(), attention: vi.fn(), views: vi.fn(), projects: vi.fn(), httpGet: vi.fn(), push: vi.fn(), query: {} as Record<string, string | string[]> }));
vi.mock("@/lib/api/missions", () => ({ missionsApi: mocks }));
vi.mock("@/lib/api/home", () => ({ homeApi: { get: mocks.home, review: mocks.review, attention: mocks.attention } }));
vi.mock("@/lib/api/missionViews", async original => ({ ...await original<object>(), missionViewsApi: { list: mocks.views } }));
vi.mock("@/lib/api/projects", () => ({ projectsApi: { listAllProjects: mocks.projects } }));
vi.mock("@/lib/api/http", async importOriginal => ({ ...await importOriginal<object>(), httpClient: { get: mocks.httpGet } }));
vi.mock("@/components/AuthGate", () => ({ AuthGate: ({ children }: { children: ReactNode }) => children }));
vi.mock("@/components/evidence/EvidencePanel", () => ({ EvidencePanel: () => <p>Linked evidence entries</p> }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { user_id: "reader" } }) }));
vi.mock("next/router", () => ({ useRouter: () => ({ query: mocks.query, push: mocks.push }) }));
import MissionsPage from "@/pages/missions";
import MissionDetailPage from "@/pages/missions/[id]";
function mission(status: MissionStatus = "draft"): ApiMission {
  return { id: "run-1", mission_id: "RUN-1", title: "Inspect research", objective: "Evidence should be auditable",
    status, project_id: "project-1", success_criteria: ["Cite evidence"], tags: [], deliverables: [],
    research_phases: {}, metadata: {}, context: {}, execution_metadata: {}, result_protocol: {},
    result_document_ids: [], result_report_id: null, result_markdown: status === "completed" ? "A sourced result" : null,
    created_at: "2026-09-13T00:00:00", updated_at: "2026-09-13T01:00:00", queued_at: null, started_at: null, completed_at: null,
  } as ApiMission;
}
function mount(page: ReactNode) { return render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}>{page}</SWRConfig>); }
beforeEach(() => {
  vi.resetAllMocks(); mocks.query = {};
  mocks.projects.mockResolvedValue([]); mocks.httpGet.mockResolvedValue([]);
  mocks.home.mockResolvedValue({ missions: { total: 143 }, attention: { total: 4 }, active_runs: { total: 1 } });
  mocks.list.mockResolvedValue({ data: [mission("queued")], pagination: { total: 143, pages: 8, page: 1, page_size: 20 } });
  mocks.get.mockResolvedValue(mission());
  mocks.attention.mockResolvedValue({ generated_at: "2026-09-14T00:00:00", dashboards: [{ key: "at_risk", total: 3 }, { key: "unreviewed", total: 1 }] });
  mocks.views.mockResolvedValue({ items: [] });
});
it("uses server totals and query filters and never invents a queue position", async () => {
  mocks.query = { view: "queue", project_id: "project-1", page: "2" };
  mount(<MissionsPage />);
  expect(await screen.findByText("143 matching missions")).toBeVisible();
  expect(mocks.list).toHaveBeenCalledWith({ view: "queue", project_id: "project-1", page: 2, page_size: 20, status: undefined });
  expect(screen.queryByText(/#1|5 min|1 in queue/)).toBeNull();
  expect(screen.getByText(/Queue position and wait time are not reported/)).toBeVisible();
  fireEvent.change(screen.getByLabelText("Status"), { target: { value: "queued" } });
  expect(mocks.push).toHaveBeenCalledWith({ pathname: "/missions", query: { view: "queue", project_id: "project-1", page: 1, status: "queued" } }, undefined, { shallow: true });
});
it.each(["draft", "queued", "in_progress", "completed", "blocked", "cancelled", "validation_failed"] as MissionStatus[])("renders %s with actions appropriate to one execution", async status => {
  mocks.query = { id: "run-1" }; mocks.get.mockResolvedValue(mission(status));
  mount(<MissionDetailPage />);
  expect(await screen.findByRole("heading", { name: "Inspect research" })).toBeVisible();
  expect(Boolean(screen.queryByRole("button", { name: "Submit to DeepSearch" }))).toBe(status === "draft");
  expect(Boolean(screen.queryByRole("button", { name: "Edit Mission" }))).toBe(status === "draft");
  expect(Boolean(screen.queryByRole("button", { name: "Cancel run" }))).toBe(["queued", "in_progress"].includes(status));
  expect(Boolean(screen.queryByRole("button", { name: "Re-run" }))).toBe(["completed", "blocked", "cancelled", "validation_failed"].includes(status));
  fireEvent.click(screen.getByRole("tab", { name: "Results" }));
  if (status === "completed") expect(screen.getByText("A sourced result")).toBeVisible();
  else expect(screen.getByText("No results recorded yet.")).toBeVisible();
  fireEvent.keyDown(screen.getByRole("tab", { name: "Results" }), { key: "ArrowRight" });
  expect(screen.getByRole("tab", { name: "Evidence" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Linked evidence entries")).toBeVisible();
});
it("requires the shared confirmation before cancel and refreshes the persisted status", async () => {
  mocks.query = { id: "run-1" }; mocks.get.mockResolvedValue(mission("queued"));
  mocks.update.mockImplementation(async () => { mocks.get.mockResolvedValue(mission("cancelled")); return mission("cancelled"); });
  mount(<MissionDetailPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Cancel run" }));
  expect(mocks.update).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  await waitFor(() => expect(mocks.update).toHaveBeenCalledWith("run-1", { status: "cancelled" }));
  expect(await screen.findByRole("button", { name: "Re-run" })).toBeVisible();
});
it("prepares a new run only after confirmation without mutating the old result", async () => {
  mocks.query = { id: "run-1" }; mocks.get.mockResolvedValue(mission("completed"));
  mount(<MissionDetailPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Re-run" }));
  expect(mocks.push).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  await waitFor(() => expect(mocks.push).toHaveBeenCalledWith({ pathname: "/missions/new", query: { from: "run-1" } }));
  expect(mocks.update).not.toHaveBeenCalled();
});

it("preserves repeated URL reasons in queries and clears them when leaving attention", async () => {
  mocks.query = { view: "attention", reason: ["blocked", "stalled"], page: "2" };
  mount(<MissionsPage />);
  await screen.findByText("143 matching missions");
  expect(mocks.list).toHaveBeenCalledWith(expect.objectContaining({ reason: ["blocked", "stalled"], page: 2 }));
  expect(screen.getByLabelText("Blocked")).toBeChecked();
  expect(screen.getByLabelText("Stalled queue")).toBeChecked();
  fireEvent.click(screen.getByLabelText("Blocked"));
  expect(mocks.push).toHaveBeenLastCalledWith({ pathname: "/missions", query: { view: "attention", reason: ["stalled"], page: 1 } }, undefined, { shallow: true });
  fireEvent.click(screen.getByRole("button", { name: "Queue", exact: true }));
  expect(mocks.push).toHaveBeenLastCalledWith({ pathname: "/missions", query: { view: "queue", page: 1 } }, undefined, { shallow: true });
});
