import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
import type { ApiMission, MissionStatus } from "@/types/mission";
const mocks = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn(), update: vi.fn(), markViewed: vi.fn(), projects: vi.fn(), httpGet: vi.fn(), push: vi.fn(), replace: vi.fn(), query: {} as Record<string, string | string[]> }));
vi.mock("@/lib/api/missions", () => ({ missionsApi: mocks }));
vi.mock("@/lib/api/activity", async original => ({ ...await original<object>(), activityApi: { markViewed: mocks.markViewed, summary: vi.fn().mockResolvedValue({ new_total: 0, by_type: {} }) } }));
vi.mock("@/lib/api/projects", () => ({ projectsApi: { listAllProjects: mocks.projects } }));
vi.mock("@/lib/api/http", async importOriginal => ({ ...await importOriginal<object>(), httpClient: { get: mocks.httpGet } }));
vi.mock("@/components/AuthGate", () => ({ AuthGate: ({ children }: { children: ReactNode }) => children }));
vi.mock("@/components/evidence/EvidencePanel", () => ({ EvidencePanel: () => <p>Linked evidence entries</p> }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { user_id: "reader" } }) }));
// The mission detail tab is URL-addressable, so the page calls router.replace (next-step #340).
vi.mock("next/router", () => ({ useRouter: () => ({ query: mocks.query, pathname: "/missions/[id]", push: mocks.push, replace: mocks.replace }) }));
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
  mocks.markViewed.mockResolvedValue({ viewed: 1, new_total: 0 });
  mocks.list.mockResolvedValue({ data: [mission("queued")], pagination: { total: 143, pages: 8, page: 1, page_size: 20 } });
  mocks.get.mockResolvedValue(mission());
});
it("uses server totals, query filters and recency sorts, and never pins rows by status", async () => {
  mocks.query = { project_id: "project-1", page: "2", sort: "updated_desc" };
  mount(<MissionsPage />);
  expect(await screen.findByText("143 matching missions")).toBeVisible();
  expect(mocks.list).toHaveBeenCalledWith({ project_id: "project-1", page: 2, page_size: 20, status: undefined, sort: "updated_desc" });
  expect(screen.queryByText(/#1|5 min|1 in queue|Needs attention|appear first|Workspace totals|Dashboards|Save view/)).toBeNull();
  expect(screen.getByLabelText("Sort")).toHaveValue("updated_desc");
  fireEvent.change(screen.getByLabelText("Status"), { target: { value: "queued" } });
  expect(mocks.push).toHaveBeenCalledWith({ pathname: "/missions", query: { project_id: "project-1", sort: "updated_desc", page: 1, status: "queued" } }, undefined, { shallow: true });
  fireEvent.change(screen.getByLabelText("Sort"), { target: { value: "created_desc" } });
  expect(mocks.push).toHaveBeenLastCalledWith({ pathname: "/missions", query: { project_id: "project-1", page: 1 } }, undefined, { shallow: true });
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

it("marks a mission viewed at its current revision when its page opens", async () => {
  mocks.query = { id: "run-1" }; mocks.get.mockResolvedValue(mission("completed"));
  mount(<MissionDetailPage />);
  await screen.findByRole("heading", { name: "Inspect research" });
  await waitFor(() => expect(mocks.markViewed).toHaveBeenCalledWith([{ type: "mission", id: "run-1", occurred_at: "2026-09-13T01:00:00" }]));
  expect(screen.queryByRole("button", { name: "Mark reviewed" })).toBeNull();
});
it("orients a draft reached from the Librarian once, and never a draft opened directly", async () => {
  // LIB-2 (decision #527): the create-then-submit shape is explained, not removed.
  window.localStorage.clear();
  mocks.query = { id: "run-1", from: "librarian" };
  const first = mount(<MissionDetailPage />);
  const notice = await screen.findByRole("region", { name: "Next step" });
  expect(notice).toHaveTextContent("Nothing runs until you press Submit to DeepSearch");
  expect(within(notice).getByText("Run it").closest("li")).toHaveAttribute("aria-current", "step");
  fireEvent.click(within(notice).getByRole("button", { name: "Don't show this again" }));
  expect(screen.queryByRole("region", { name: "Next step" })).toBeNull();
  expect(window.localStorage.getItem("tracelab.librarian.orientation.v1:reader")).toBe("dismissed");
  first.unmount();

  window.localStorage.clear();
  mocks.query = { id: "run-1" };
  mount(<MissionDetailPage />);
  expect(await screen.findByRole("heading", { name: "Inspect research" })).toBeVisible();
  expect(screen.queryByRole("region", { name: "Next step" })).toBeNull();
});
