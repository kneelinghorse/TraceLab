import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";

import LibrarianPage from "@/pages/librarian";

const mocks = vi.hoisted(() => ({
  turn: vi.fn(),
  draft: vi.fn(),
  createMission: vi.fn(),
  listAllProjects: vi.fn(),
  createProject: vi.fn(),
  push: vi.fn(),
}));
vi.mock("@/lib/api/librarian", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/librarian")>("@/lib/api/librarian");
  return { ...actual, librarianApi: { turn: mocks.turn, draft: mocks.draft, createMission: mocks.createMission } };
});
vi.mock("@/lib/api/projects", () => ({ projectsApi: { listAllProjects: mocks.listAllProjects, createProject: mocks.createProject } }));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ isReady: true, isAuthenticated: true, user: { user_id: "reader" } }),
}));
vi.mock("@/components/AuthGate", () => ({ AuthGate: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock("next/router", () => ({ useRouter: () => ({ query: {}, push: mocks.push, pathname: "/librarian" }) }));

const projectId = "10000000-0000-4000-8000-000000000001";
const evidenceId = "20000000-0000-4000-8000-000000000002";

function page() {
  render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}>
      <LibrarianPage />
    </SWRConfig>,
  );
}

async function chooseProject() {
  await screen.findByRole("option", { name: "Onboarding" });
  fireEvent.change(screen.getByRole("combobox", { name: "Project" }), { target: { value: projectId } });
}

beforeEach(() => {
  vi.resetAllMocks();
  mocks.listAllProjects.mockResolvedValue([{ id: projectId, name: "Onboarding" }]);
  mocks.push.mockResolvedValue(true);
});

describe("Librarian page", () => {
  it("renders world knowledge as prose and corpus claims as cited passages", async () => {
    mocks.turn.mockResolvedValue({
      segments: [
        { kind: "prose", text: "Onboarding research usually starts with the audience.", citations: [] },
        { kind: "corpus_claim", text: "Your project already notes onboarding confusion.", citations: [evidenceId] },
      ],
      suggested_action: null,
      evidence: [{ id: evidenceId, claim: "Confusion", source_url: "https://example.test", disposition: "supporting", href: `/evidence/${evidenceId}` }],
      withheld_count: 0,
      usage: null,
      model: "fake",
    });
    page();
    await chooseProject();
    fireEvent.change(screen.getByLabelText("Message the Librarian"), { target: { value: "What do we know about onboarding?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    const log = await screen.findByRole("log");
    expect(await within(log).findByText("Onboarding research usually starts with the audience.")).toBeVisible();
    const claim = within(log).getByText("Your project already notes onboarding confusion.").closest("[data-kind='corpus_claim']");
    expect(claim).not.toBeNull();
    expect(within(claim as HTMLElement).getByRole("link", { name: "Evidence 1" })).toHaveAttribute("href", `/evidence/${evidenceId}`);
    expect(within(log).getByText("What do we know about onboarding?")).toBeVisible();

    const [messages, sentProject] = mocks.turn.mock.calls[0];
    expect(sentProject).toBe(projectId);
    expect(messages).toEqual([{ role: "user", content: "What do we know about onboarding?" }]);
  });

  it("shows a withheld notice instead of an unproven claim and keeps talking without a project", async () => {
    mocks.turn.mockResolvedValue({
      segments: [{ kind: "withheld", text: "A statement about this project's evidence was withheld.", citations: [] }],
      suggested_action: null,
      evidence: [],
      withheld_count: 1,
      usage: null,
      model: "fake",
    });
    page();
    await screen.findByRole("option", { name: "Onboarding" });
    fireEvent.click(screen.getByRole("button", { name: /abandon onboarding/ }));
    expect(await screen.findByRole("note")).toHaveTextContent("was withheld");
    expect(mocks.turn.mock.calls[0][1]).toBeNull();
    expect(screen.getByRole("button", { name: "Draft a mission" })).toBeDisabled();
  });

  it("drafts a mission from the transcript, shows the compiled contract, and creates it on confirmation", async () => {
    mocks.turn.mockResolvedValue({
      segments: [{ kind: "prose", text: "Who is the audience?", citations: [] }],
      suggested_action: "draft_mission",
      evidence: [],
      withheld_count: 0,
      usage: null,
      model: "fake",
    });
    mocks.draft.mockResolvedValue({
      draft: {
        mission_id: "ONBOARD-1",
        title: "Onboarding friction",
        objective: "Find where new users drop off during onboarding and why.",
        success_criteria: ["Name the top three drop-off points", "Cite two sources per point"],
        required_entities: ["onboarding"],
        constraints: ["Prefer sources published in 2025 or 2026"],
        deliverable_format: "Markdown report",
        deliverables: [],
        tags: [],
      },
      preview: {
        contract_version: "1.0", compiler_revision: "24e88100abcdef", fidelity: "structural_only", named_entities: ["onboarding"],
        objectives: [{}, {}, {}], evidence_slots: [{}, {}], acceptance_checks: [{}], deliverable_schemas: [], coverage_thresholds: {}, validation_thresholds: {},
      },
      preview_error: null,
      lint_errors: [],
      lint_warnings: [{ rule: "broad", field: "objective", message: "Objective is broad.", suggestion: "Name entities." }],
      notes: ["No required_entities were named."],
      usage: null,
      model: "fake",
    });
    mocks.createMission.mockResolvedValue({ mission: { id: "mission-uuid", mission_id: "ONBOARD-1" }, created: true });

    page();
    await chooseProject();
    fireEvent.change(screen.getByLabelText("Message the Librarian"), { target: { value: "Research onboarding drop-off for new design teams." } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("The Librarian thinks there is enough here for a mission.")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Draft a mission" }));
    const panel = await screen.findByRole("region", { name: "Mission draft" });
    expect(within(panel).getByRole("heading", { name: "Onboarding friction" })).toBeVisible();
    expect(within(panel).getByText(/3 research objectives · 2 evidence slots · 1 acceptance checks · 0 deliverable schemas/)).toBeVisible();
    expect(within(panel).getByText(/Objective is broad\./)).toBeVisible();
    expect(within(panel).getByText("No required_entities were named.")).toBeVisible();
    expect(mocks.draft).toHaveBeenCalledWith(
      [
        { role: "user", content: "Research onboarding drop-off for new design teams." },
        { role: "assistant", content: "Who is the audience?" },
      ],
      projectId,
    );

    fireEvent.click(within(panel).getByRole("button", { name: "Create draft mission" }));
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/missions/mission-uuid"));
    expect(mocks.createMission).toHaveBeenCalledWith(expect.objectContaining({ mission_id: "ONBOARD-1" }), projectId);
  });

  it("lets a user with no project create one inline and selects it", async () => {
    mocks.listAllProjects.mockResolvedValueOnce([]).mockResolvedValue([{ id: projectId, name: "Fresh start" }]);
    mocks.createProject.mockResolvedValue({ id: projectId, name: "Fresh start" });
    page();
    expect(await screen.findByText(/Without a project the Librarian can only plan/)).toBeVisible();
    fireEvent.change(screen.getByLabelText("New project"), { target: { value: "Fresh start" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(mocks.createProject).toHaveBeenCalledWith({ name: "Fresh start" }));
    await waitFor(() => expect((screen.getByRole("combobox", { name: "Project" }) as HTMLSelectElement).value).toBe(projectId));
    expect(await screen.findByText(/Missions will be created in/)).toBeVisible();
  });
});
