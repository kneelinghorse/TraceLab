import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";

import { HttpError } from "@/lib/api/http";
import LibrarianPage from "@/pages/librarian";

const mocks = vi.hoisted(() => ({
  turn: vi.fn(),
  draft: vi.fn(),
  createMission: vi.fn(),
  listAllProjects: vi.fn(),
  createProject: vi.fn(),
  listSpaces: vi.fn(),
  push: vi.fn(),
  query: {} as Record<string, string>,
  pedrSearch: vi.fn(),
  execute: vi.fn(),
  savedList: vi.fn(),
  createSaved: vi.fn(),
  getDocument: vi.fn(),
  createCollection: vi.fn(),
  addChunk: vi.fn(),
}));
vi.mock("@/lib/api/librarian", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/librarian")>("@/lib/api/librarian");
  return { ...actual, librarianApi: { turn: mocks.turn, draft: mocks.draft, createMission: mocks.createMission } };
});
vi.mock("@/lib/api/projects", () => ({ projectsApi: { listAllProjects: mocks.listAllProjects, createProject: mocks.createProject } }));
vi.mock("@/lib/api/spaces", () => ({ spacesApi: { list: mocks.listSpaces } }));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ isReady: true, isAuthenticated: true, user: { user_id: "reader" } }),
}));
vi.mock("@/components/AuthGate", () => ({ AuthGate: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock("@/lib/api/search", () => ({ searchApi: { pedrSearch: mocks.pedrSearch } }));
vi.mock("@/lib/api/savedSearches", () => ({ savedSearchesApi: { execute: mocks.execute, list: mocks.savedList, create: mocks.createSaved } }));
vi.mock("@/lib/api/documents", () => ({ documentsApi: { getDocument: mocks.getDocument } }));
vi.mock("@/lib/api/collections", () => ({ collectionsApi: { create: mocks.createCollection, addChunk: mocks.addChunk } }));
vi.mock("next/router", () => ({ useRouter: () => ({ query: mocks.query, push: mocks.push, pathname: "/librarian" }) }));

const projectId = "10000000-0000-4000-8000-000000000001";
const evidenceId = "20000000-0000-4000-8000-000000000002";

function page(swr: Record<string, unknown> = {}) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false, ...swr }}>
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
  window.localStorage.clear();
  mocks.listAllProjects.mockResolvedValue([{ id: projectId, name: "Onboarding" }]);
  // One Space, the reader's own: no picker, as for most members.
  mocks.listSpaces.mockResolvedValue([{ id: "space-mine", name: "Reader's Space", created_at: "", personal_owner_id: "reader" }]);
  mocks.push.mockResolvedValue(true);
  mocks.query = {};
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
    // WALK-1 finding 4: when the model says there is enough, Draft is the primary action.
    expect(screen.getByRole("button", { name: "Draft a mission" })).toHaveAttribute("data-suggested", "true");

    fireEvent.click(screen.getByRole("button", { name: "Draft a mission" }));
    const panel = await screen.findByRole("region", { name: "Mission draft" });
    // WALK-1 finding 3: a successful draft must be impossible to miss. Focus lands in an
    // effect after the panel renders, so wait for it rather than race it (seen on cold runs).
    await waitFor(() => expect(panel).toHaveFocus());
    expect(await screen.findByText("Your draft is ready below. Review it, then create it.")).toBeVisible();
    expect(within(panel).getByText(/Next: the mission page, where you can edit the draft and press Submit to DeepSearch/)).toBeVisible();
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
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/missions/mission-uuid?from=librarian"));
    // The draft is consumed; the conversation stays for the next one.
    expect(JSON.parse(window.localStorage.getItem("tracelab.librarian.v1:reader") ?? "{}")).toMatchObject({ projectId, draft: null });
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

  // PERSONAL-2 (decision #533): the picker appears only for someone in more than one Space.
  it("shows no Space picker to someone whose only Space is their own", async () => {
    page();
    await screen.findByRole("option", { name: "Onboarding" });
    await waitFor(() => expect(mocks.listSpaces).toHaveBeenCalled());
    expect(screen.queryByRole("combobox", { name: "Space" })).toBeNull();
  });

  it("lets a member of a shared Space create the new project there", async () => {
    mocks.listSpaces.mockResolvedValue([
      { id: "space-mine", name: "Reader's Space", created_at: "", personal_owner_id: "reader" },
      { id: "space-parts", name: "Parts Town", created_at: "", personal_owner_id: null },
    ]);
    mocks.createProject.mockResolvedValue({ id: projectId, name: "Catalog audit" });
    page();
    const picker = (await screen.findByRole("combobox", { name: "Space" })) as HTMLSelectElement;
    expect(picker.value).toBe("");
    expect(within(picker).getByRole("option", { name: "My Space" })).toBeInTheDocument();
    fireEvent.change(picker, { target: { value: "space-parts" } });
    fireEvent.change(screen.getByLabelText("New project"), { target: { value: "Catalog audit" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() =>
      expect(mocks.createProject).toHaveBeenCalledWith({ name: "Catalog audit", workspace_id: "space-parts" }),
    );
  });

  it("keeps the conversation and project when the page is left and reopened, until the user starts over", async () => {
    // WALK-1 finding 1: four paid turns and a draft vanished on one route change.
    mocks.turn.mockResolvedValue({
      segments: [{ kind: "prose", text: "Start with who abandons and when.", citations: [] }],
      suggested_action: null, evidence: [], withheld_count: 0, usage: null, model: "fake",
    });
    const first = page();
    await chooseProject();
    fireEvent.change(screen.getByLabelText("Message the Librarian"), { target: { value: "Why do users abandon onboarding?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Start with who abandons and when.")).toBeVisible();
    first.unmount();

    page();
    const log = await screen.findByRole("log");
    expect(await within(log).findByText("Start with who abandons and when.")).toBeVisible();
    expect(within(log).getByText("Why do users abandon onboarding?")).toBeVisible();
    await waitFor(() => expect((screen.getByRole("combobox", { name: "Project" }) as HTMLSelectElement).value).toBe(projectId));
    expect(mocks.turn).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Start over" }));
    expect(within(screen.getByRole("log")).queryByText("Start with who abandons and when.")).toBeNull();
    expect(window.localStorage.getItem("tracelab.librarian.v1:reader")).toBeNull();
  });

  it("explains the three steps until the user asks it not to", async () => {
    // WALK-1 finding 6 and Derek's "dont show me this anymore".
    const first = page();
    await screen.findByRole("option", { name: "Onboarding" });
    const steps = screen.getByRole("navigation", { name: "Where you are" });
    expect(within(steps).getByText("Shape it").closest("li")).toHaveAttribute("aria-current", "step");
    fireEvent.click(within(steps).getByRole("button", { name: "Don't show this again" }));
    expect(screen.queryByRole("navigation", { name: "Where you are" })).toBeNull();
    first.unmount();

    page();
    await screen.findByRole("option", { name: "Onboarding" });
    expect(screen.queryByRole("navigation", { name: "Where you are" })).toBeNull();
  });
});

// QA-1: asking a project's documents. The answer's every citation opens the chunk it
// came from, a question the project cannot support is refused and asserts nothing,
// and the answer budget the user chose goes out with the request.
describe("Librarian page, asking the documents", () => {
  const documentId = "30000000-0000-4000-8000-000000000003";
  const chunkId = "40000000-0000-4000-8000-000000000004";
  const chunk = {
    id: chunkId,
    document_id: documentId,
    document_name: "qdrant-on-railway.md",
    chunk_index: 9,
    snippet: "The Hobby plan bill is approximately $48-$63 a month.",
    href: `/documents/${documentId}?chunk=${chunkId}&index=9`,
  };

  function answer(overrides: Record<string, unknown> = {}) {
    return {
      segments: [
        { kind: "corpus_claim", text: "The bill is **$48–$63** a month.", citations: [chunkId] },
        { kind: "prose", text: "Managed hosting usually costs more.", citations: [] },
      ],
      suggested_action: null,
      evidence: [],
      chunks: [chunk],
      no_evidence: false,
      withheld_count: 0,
      usage: null,
      model: "gpt-5.1",
      ...overrides,
    };
  }

  async function ask(question: string) {
    fireEvent.change(screen.getByLabelText("Message the Librarian"), { target: { value: question } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  }

  it("sends the chosen budget and links each citation to the chunk it came from", async () => {
    mocks.turn.mockResolvedValue(answer());
    page();
    await chooseProject();
    fireEvent.click(screen.getByRole("radio", { name: "Ask the documents" }));
    expect(screen.getByRole("radio", { name: "Short answer" })).toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: "Full synthesis" }));
    await ask("What does self-hosting Qdrant cost?");

    const log = await screen.findByRole("log");
    const claim = (await within(log).findByText(/a month\./)).closest("[data-kind='corpus_claim']") as HTMLElement;
    expect(claim).not.toBeNull();
    expect(within(claim).getByText("From this project's documents")).toBeVisible();
    expect(within(claim).getByRole("link", { name: "qdrant-on-railway.md #9" })).toHaveAttribute("href", chunk.href);
    // Uncited text is not dressed as a claim.
    expect(within(log).getByText("Managed hosting usually costs more.").closest("[data-kind='corpus_claim']")).toBeNull();

    const [messages, sentProject, options] = mocks.turn.mock.calls[0];
    expect(messages).toEqual([{ role: "user", content: "What does self-hosting Qdrant cost?" }]);
    expect(sentProject).toBe(projectId);
    expect(options).toEqual({ maxTokens: 2000 });
  });

  it("asks for a short answer unless the user chooses a full synthesis", async () => {
    mocks.turn.mockResolvedValue(answer());
    page();
    await chooseProject();
    fireEvent.click(screen.getByRole("radio", { name: "Ask the documents" }));
    await ask("What does it cost?");
    await waitFor(() => expect(mocks.turn).toHaveBeenCalledWith(expect.any(Array), projectId, { maxTokens: 600 }));
  });

  it("renders a refusal as a note that asserts nothing, and keeps it that way after a reload", async () => {
    mocks.turn.mockResolvedValue(
      answer({
        segments: [{ kind: "prose", text: "Nothing in this project answers that question.", citations: [] }],
        chunks: [],
        no_evidence: true,
      }),
    );
    const first = page();
    await chooseProject();
    fireEvent.click(screen.getByRole("radio", { name: "Ask the documents" }));
    await ask("How does Kubernetes autoscale pods?");

    const refusal = await screen.findByRole("note");
    expect(refusal).toHaveAttribute("data-kind", "refusal");
    expect(refusal).toHaveTextContent("Nothing in this project answers that question.");
    const log = screen.getByRole("log");
    expect(log.querySelector("[data-kind='corpus_claim']")).toBeNull();
    expect(within(log).queryByRole("link")).toBeNull();
    first.unmount();

    page();
    expect(await screen.findByRole("note")).toHaveAttribute("data-kind", "refusal");
  });

  it("cannot ask the documents without a project", async () => {
    page();
    await screen.findByRole("option", { name: "Onboarding" });
    expect(screen.getByRole("radio", { name: "Ask the documents" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "Talk it through" })).toBeChecked();
    expect(screen.queryByRole("radio", { name: "Full synthesis" })).toBeNull();
  });
});

// QA-2: search absorbed into the Librarian. A phrase lists the ranked chunks that match
// it, each opening at its place in the document; the list can be kept as a collection;
// a saved search runs here, through the call that counts its runs (decision #545).
describe("Librarian page, listing the chunks", () => {
  const firstDocument = "50000000-0000-4000-8000-000000000005";
  const secondDocument = "60000000-0000-4000-8000-000000000006";
  const chunks = ["70000000-0000-4000-8000-000000000007", "80000000-0000-4000-8000-000000000008", "90000000-0000-4000-8000-000000000009"];

  function hit(chunk_id: string, document_id: string | undefined, chunk_index: number, content: string, rrf_score: number) {
    return { chunk_id, content, document_id, project_id: projectId, chunk_index, rrf_score, rrf_rank: 1, layer_ranks: {}, layer_scores: {}, confidence: 0.5, criticality: 0.5, quality_score: 1, quality_gates_passed: 0, contributing_layers: ["lexical"] };
  }
  const hits = [
    hit(chunks[0], firstDocument, 3, "Users stall at the second onboarding step.", 0.033),
    hit(chunks[1], secondDocument, 0, "Pricing confusion drives early churn.", 0.032),
    hit(chunks[2], undefined, 4, "A related finding with no parent document.", 0.016),
  ];

  beforeEach(() => {
    mocks.pedrSearch.mockResolvedValue({ results: hits, metadata: null });
    mocks.getDocument.mockImplementation(async (id: string) => ({ id, name: id === firstDocument ? "interviews.md" : "survey.pdf" }));
    mocks.savedList.mockResolvedValue({ items: [], limit_per_user: 50 });
  });

  it("puts the phrase in the URL and never sends it to the Librarian model", async () => {
    // The URL is what /search?q= redirects to and what a reload reruns.
    page();
    await chooseProject();
    fireEvent.click(screen.getByRole("radio", { name: "List the chunks" }));
    fireEvent.change(screen.getByLabelText("Message the Librarian"), { target: { value: "onboarding friction" } });
    fireEvent.click(screen.getByRole("button", { name: "List" }));
    expect(mocks.push).toHaveBeenCalledWith({ pathname: "/librarian", query: { q: "onboarding friction", project: projectId } }, undefined, { shallow: true });
    expect(mocks.turn).not.toHaveBeenCalled();
    expect(screen.queryByRole("log")?.textContent).not.toContain("onboarding friction");
  });

  it("lists the ranked chunks for the URL's phrase, each linking to its place in its document", async () => {
    mocks.query = { q: "onboarding friction", project: projectId };
    page();
    const list = await screen.findByRole("region", { name: "Matching chunks" });
    expect(screen.getByRole("radio", { name: "List the chunks" })).toBeChecked();
    expect(mocks.pedrSearch).toHaveBeenCalledWith({ query: "onboarding friction", top_k: 20, project_id: projectId });
    expect(await within(list).findByRole("heading", { name: "3 chunks match “onboarding friction”" })).toBeVisible();
    expect(within(list).getByText(/^In Onboarding, best match first/)).toBeVisible();

    const rows = within(list).getAllByRole("listitem");
    expect(rows.map((row) => row.querySelector("p")?.textContent)).toEqual(["1.interviews.md #3", "2.survey.pdf #0", "3.Chunk without a document #4"]);
    expect(await within(rows[0]).findByRole("link", { name: "interviews.md #3" })).toHaveAttribute("href", `/documents/${firstDocument}?chunk=${chunks[0]}&index=3`);
    expect(within(rows[1]).getByRole("link", { name: "survey.pdf #0" })).toHaveAttribute("href", `/documents/${secondDocument}?chunk=${chunks[1]}&index=0`);
    // A chunk with no document cannot be opened, so it is not dressed as a link.
    expect(within(rows[2]).queryByRole("link")).toBeNull();
    expect(within(rows[0]).getByText("Score 0.0330")).toBeVisible();
    expect(within(rows[0]).getByText("Users stall at the second onboarding step.")).toBeVisible();
    expect(mocks.turn).not.toHaveBeenCalled();
  });

  it("lists across every readable project when no project is named", async () => {
    mocks.query = { q: "pricing" };
    page();
    const list = await screen.findByRole("region", { name: "Matching chunks" });
    expect(await within(list).findByText(/^Across all your projects, best match first/)).toBeVisible();
    expect(mocks.pedrSearch).toHaveBeenCalledWith({ query: "pricing", top_k: 20, project_id: undefined });
  });

  it("keeps the list as one collection in rank order, and a retry adds only what is missing", async () => {
    // A failed add must not leave a second, duplicate collection behind on retry.
    mocks.query = { q: "onboarding friction", project: projectId };
    mocks.createCollection.mockResolvedValue({ id: "collection-1", name: "onboarding friction" });
    mocks.addChunk.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error("The chunk could not be added.")).mockResolvedValue({});
    page();
    const list = await screen.findByRole("region", { name: "Matching chunks" });
    expect(within(list).getByLabelText("Collection name")).toHaveValue("onboarding friction");
    fireEvent.click(await within(list).findByRole("button", { name: "Save 3 chunks as a collection" }));

    expect(await within(list).findByRole("alert")).toHaveTextContent("Created onboarding friction with 1 of 3 chunks. The chunk could not be added.");
    fireEvent.click(within(list).getByRole("button", { name: "Add the remaining 2" }));
    const saved = await within(list).findByText(/^Saved 3 chunks to/);
    expect(within(saved).getByRole("link", { name: "onboarding friction" })).toHaveAttribute("href", "/collections/collection-1");

    expect(mocks.createCollection).toHaveBeenCalledTimes(1);
    expect(mocks.createCollection).toHaveBeenCalledWith({ name: "onboarding friction" });
    expect(mocks.addChunk.mock.calls.map(([collection, body]) => [collection, body.chunk_id])).toEqual([
      ["collection-1", chunks[0]],
      ["collection-1", chunks[1]],
      ["collection-1", chunks[1]],
      ["collection-1", chunks[2]],
    ]);
  });

  it("saves the phrase as a saved search with its project and list size", async () => {
    mocks.query = { q: "onboarding friction", project: projectId };
    mocks.createSaved.mockResolvedValue({ id: "saved-1" });
    page();
    const list = await screen.findByRole("region", { name: "Matching chunks" });
    fireEvent.click(await within(list).findByRole("button", { name: "Save current search" }));
    fireEvent.click(within(list).getByRole("button", { name: "Save search" }));
    expect(await within(list).findByText(/^Search saved\./)).toBeVisible();
    expect(mocks.createSaved).toHaveBeenCalledWith(expect.objectContaining({ query_text: "onboarding friction", top_k: 20, filters: { project_id: projectId } }));
  });

  it("runs a saved search once through the call that counts its runs, and shows no answer", async () => {
    mocks.query = { saved: "saved-1" };
    mocks.execute.mockResolvedValue({
      saved_search: { id: "saved-1", name: "Weekly onboarding", query_text: "onboarding", filters: { project_id: projectId }, top_k: 5 },
      semantic: { results: [{ chunk_id: chunks[0], content: "Users stall at the second onboarding step.", document_id: firstDocument, project_id: projectId, chunk_index: 3, score: 0.82 }] },
      rag: { answer: "A synthesized answer the chunk list does not show." },
    });
    // No focus throttle, so a focus event right after mount would revalidate if the list allowed it.
    page({ focusThrottleInterval: 0 });
    const list = await screen.findByRole("region", { name: "Matching chunks" });
    expect(await within(list).findByRole("heading", { name: "Saved search “Weekly onboarding”: 1 chunk matches" })).toBeVisible();
    expect(within(list).getByText(/^In Onboarding, best match first, for “onboarding”/)).toBeVisible();
    expect(await within(list).findByRole("link", { name: "interviews.md #3" })).toHaveAttribute("href", `/documents/${firstDocument}?chunk=${chunks[0]}&index=3`);
    expect(screen.queryByText("A synthesized answer the chunk list does not show.")).toBeNull();
    expect(mocks.pedrSearch).not.toHaveBeenCalled();

    // Each execute call counts a run and spends a model call, so returning to the tab must not rerun it.
    fireEvent(window, new Event("focus"));
    document.dispatchEvent(new Event("visibilitychange"));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mocks.execute).toHaveBeenCalledTimes(1);
    expect(mocks.execute).toHaveBeenCalledWith("saved-1");
  });

  it("says a deleted saved search no longer exists instead of offering a retry", async () => {
    mocks.query = { saved: "gone" };
    mocks.execute.mockRejectedValue(new HttpError("Saved search not found.", 404));
    page();
    const list = await screen.findByRole("region", { name: "Matching chunks" });
    expect(await within(list).findByRole("alert")).toHaveTextContent("This saved search no longer exists");
    expect(within(list).queryByRole("button", { name: "Retry" })).toBeNull();
  });
});
