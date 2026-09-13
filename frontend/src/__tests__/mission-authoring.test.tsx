import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

it("seeds collection instructions and document references into a reviewed draft before submission", async () => {
  const seed = { collection_id: "context", title: "Research: Source context", project_id: projectId,
    background: "Compare the original sources.\nDocument doc-1", references: [{ title: "Original source", document_id: "doc-1", href: "/documents/doc-1" }],
    context: { collection_id: "context", document_ids: ["doc-1"] } };
  const onSuccess = form({ source: undefined, seed });
  await screen.findByRole("option", { name: "Research" });
  expect(screen.getByLabelText(/Title/)).toHaveValue(seed.title);
  expect(screen.getByLabelText("Background")).toHaveValue(seed.background);
  expect(mocks.create).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText(/Objective/), { target: { value: "Compare the supplied primary research sources" } });
  fireEvent.change(screen.getByRole("textbox", { name: "Success Criteria 1" }), { target: { value: "Preserve contradictions and cite the original documents" } });
  fireEvent.click(screen.getByRole("button", { name: "Submit to DeepSearch" }));
  await waitFor(() => expect(onSuccess).toHaveBeenCalled());
  expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ status: "draft", background: seed.background, context: seed.context, references: seed.references }));
  expect(mocks.create.mock.calls[0][0]).not.toHaveProperty("collection_id");
  expect(mocks.submitToDeepSearch).toHaveBeenCalledWith("saved");
});

it.each(["collection", "rerun"])("shows the %s destination after project options load and retains user changes", async kind => {
  let resolveProjects!: (projects: { id: string; name: string }[]) => void;
  mocks.listAllProjects.mockReturnValue(new Promise(resolve => { resolveProjects = resolve; }));
  form(kind === "collection" ? { source: undefined, seed: { collection_id: "context", title: "Sources", project_id: projectId, background: "Instructions", references: [], context: {} } } : {});
  const select = screen.getByLabelText(/Project/);
  expect(screen.queryByRole("option", { name: "Research" })).not.toBeInTheDocument();
  const otherProject = "10000000-0000-4000-8000-000000000002";
  await act(async () => resolveProjects([{ id: projectId, name: "Research" }, { id: otherProject, name: "Other destination" }]));
  await screen.findByRole("option", { name: "Research" });
  expect(select).toHaveValue(projectId);
  fireEvent.change(select, { target: { value: otherProject } });
  expect(select).toHaveValue(otherProject);
  expect(mocks.create).not.toHaveBeenCalled();
});

it("does not choose a destination project for mixed-project collection context", async () => {
  form({ source: undefined, seed: { collection_id: "context", title: "Mixed sources", project_id: null, background: "Instructions", references: [], context: { document_ids: ["a", "b"] } } });
  await screen.findByRole("option", { name: "Research" });
  expect(screen.getByLabelText(/Project/)).toHaveValue("");
  expect(mocks.create).not.toHaveBeenCalled();
});

it("preserves document identity when editing or removing references with duplicate filenames", async () => {
  const refs = ["first", "second", "third"].map(id => ({ title: "report.md", document_id: id, href: `/documents/${id}` }));
  form({ source: { ...source, references: refs } });
  await screen.findByRole("option", { name: "Research" });
  fireEvent.change(screen.getByRole("textbox", { name: "References 1", exact: true }), { target: { value: "Renamed source" } });
  fireEvent.click(screen.getByRole("button", { name: "Remove item 2", exact: true }));
  fireEvent.click(screen.getByRole("button", { name: "Save and preview" }));
  await screen.findByText("revision-1");
  expect(mocks.create.mock.calls[0][0].references).toEqual([{ ...refs[0], title: "Renamed source" }, refs[2]]);
});
