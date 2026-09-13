import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
import { MissionForm } from "@/components/missions/MissionForm";
import type { ApiMission } from "@/types/mission";

const mocks = vi.hoisted(() => ({ create: vi.fn(), get: vi.fn(), update: vi.fn(), submitToDeepSearch: vi.fn(), previewContract: vi.fn(), listAllProjects: vi.fn() }));
vi.mock("@/lib/api/missions", () => ({ missionsApi: mocks }));
vi.mock("@/lib/api/projects", () => ({ projectsApi: mocks }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { user_id: "reader" } }) }));
const projectId = "10000000-0000-4000-8000-000000000001";
const source = {
  id: "original", mission_id: "OLD-1", title: "Auditable research", objective: "Find evidence for the research question",
  success_criteria: ["Cite primary sources"], project_id: projectId, status: "completed", tags: ["science"],
  deliverables: ["Report"], context: { instructions: "Keep scope" }, research_phases: { research: { name: "Research" } },
  metadata: { priority: "high", custom: true }, references: [{ title: "Paper", url: "https://example.test/paper" }],
  background: "Context", focus: "Question", required_entities: ["Entity"], excluded_entities: ["Excluded"], constraints: ["Primary sources"],
  deliverable_format: "markdown", min_loops: null, max_loops: null, expected_output_schema: { type: "object" },
  coverage_thresholds: { min_sources: 2 }, validation_thresholds: { structural: 0.8 },
  deepsearch_lease_token: "old-lease", result_markdown: "Old result", execution_metadata: { current_loop: 10 },
} as unknown as ApiMission;
const preview = { mission_id: "NEW-1", mission_uuid: "saved", contract_version: "1.0", compiler_revision: "revision-1", fidelity: "structural_only", named_entities: [], objectives: [], evidence_slots: [], acceptance_checks: [], deliverable_schemas: [], coverage_thresholds: {}, validation_thresholds: {} };
function form(props: Partial<React.ComponentProps<typeof MissionForm>> = {}) {
  const onSuccess = vi.fn();
  render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}><MissionForm source={source} onSuccess={onSuccess} {...props} /></SWRConfig>);
  return onSuccess;
}
beforeEach(() => {
  vi.resetAllMocks();
  mocks.listAllProjects.mockResolvedValue([{ id: projectId, name: "Research" }]);
  mocks.create.mockImplementation(async payload => ({ ...source, ...payload, id: "saved", status: "draft" }));
  mocks.get.mockResolvedValue({ ...source, id: "saved", status: "draft" });
  mocks.update.mockImplementation(async (_id, payload) => ({ ...source, ...payload, id: "saved", status: "draft" }));
  mocks.submitToDeepSearch.mockResolvedValue({ status: "queued" });
  mocks.previewContract.mockResolvedValue(preview);
});

it("saves and previews inline, preserves authored fields, and submits the same pristine draft", async () => {
  const onSuccess = form();
  await screen.findByRole("option", { name: "Research" });
  fireEvent.change(screen.getByLabelText(/Mission ID/), { target: { value: "NEW-1" } });
  fireEvent.click(screen.getByRole("button", { name: "Save and preview" }));
  expect(await screen.findByText("revision-1")).toBeVisible();
  expect(screen.getByText("structural_only")).toBeVisible();
  expect(onSuccess).not.toHaveBeenCalled();
  const payload = mocks.create.mock.calls[0][0];
  expect(payload).toMatchObject({ mission_id: "NEW-1", status: "draft", context: source.context, research_phases: source.research_phases, references: source.references, expected_output_schema: source.expected_output_schema });
  for (const key of ["id", "deepsearch_lease_token", "execution_metadata", "result_markdown"]) expect(payload).not.toHaveProperty(key);
  expect(payload.min_loops).toBeNull();
  fireEvent.change(screen.getByLabelText(/Title/), { target: { value: "Refined research" } });
  expect(await screen.findByText(/Unsaved changes/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Submit to DeepSearch" }));
  await waitFor(() => expect(onSuccess).toHaveBeenCalled());
  expect(mocks.create).toHaveBeenCalledTimes(1);
  expect(mocks.update).toHaveBeenCalledWith("saved", expect.objectContaining({ title: "Refined research" }));
  expect(mocks.submitToDeepSearch).toHaveBeenCalledWith("saved");
});

it("retains a saved draft after failed submission and maps lint errors to the field", async () => {
  mocks.submitToDeepSearch.mockRejectedValueOnce(new Error(JSON.stringify({ detail: { message: "Fix the contract", errors: [{ field: "objective", message: "Name the evidence to gather", rule: "specificity" }] } })));
  const onSuccess = form();
  await screen.findByRole("option", { name: "Research" });
  fireEvent.click(screen.getByRole("button", { name: "Submit to DeepSearch" }));
  expect(await screen.findByText("Name the evidence to gather")).toBeVisible();
  expect(onSuccess).not.toHaveBeenCalled();
  expect(screen.getByRole("link", { name: "Open saved draft" })).toHaveAttribute("href", "/missions/saved");
  fireEvent.change(screen.getByLabelText(/Objective/), { target: { value: "Find published measurements with citations" } });
  fireEvent.click(screen.getByRole("button", { name: "Submit to DeepSearch" }));
  await waitFor(() => expect(onSuccess).toHaveBeenCalled());
  expect(mocks.create).toHaveBeenCalledTimes(1);
  expect(mocks.submitToDeepSearch).toHaveBeenCalledTimes(2);
});

it("normalizes optional empty loop inputs and blocks malformed JSON before saving", async () => {
  form();
  await screen.findByRole("option", { name: "Research" });
  fireEvent.change(screen.getByLabelText("Min loops"), { target: { value: "3" } });
  fireEvent.change(screen.getByLabelText("Min loops"), { target: { value: "" } });
  fireEvent.change(screen.getByLabelText("Expected output schema"), { target: { value: "[" } });
  fireEvent.click(screen.getByRole("button", { name: "Save and preview" }));
  expect(await screen.findByText(/Invalid JSON/)).toBeVisible();
  expect(mocks.create).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Expected output schema"), { target: { value: "{}" } });
  fireEvent.click(screen.getByRole("button", { name: "Save and preview" }));
  await screen.findByText("revision-1");
  expect(mocks.create.mock.calls[0][0].min_loops).toBeNull();
});

it("does not reset a run after an ambiguous submission response", async () => {
  mocks.submitToDeepSearch.mockRejectedValueOnce(new Error("Connection lost"));
  form();
  await screen.findByRole("option", { name: "Research" });
  fireEvent.click(screen.getByRole("button", { name: "Submit to DeepSearch" }));
  await screen.findByText("Connection lost");
  mocks.get.mockResolvedValue({ ...source, id: "saved", status: "queued" });
  fireEvent.click(screen.getByRole("button", { name: "Submit to DeepSearch" }));
  expect(await screen.findByText(/already queued/)).toBeVisible();
  expect(mocks.update).not.toHaveBeenCalled();
  expect(mocks.submitToDeepSearch).toHaveBeenCalledTimes(1);
  expect(mocks.create).toHaveBeenCalledTimes(1);
});
