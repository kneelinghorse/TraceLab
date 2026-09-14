import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";

const mocks = vi.hoisted(() => ({
  router: { isReady: true, query: {} as Record<string, string | string[]> },
  auth: { isReady: true, isAuthenticated: true, user: { user_id: "alice" } },
  pedr: vi.fn(),
  semantic: vi.fn(), rag: vi.fn(), replay: vi.fn(), savedExecute: vi.fn(), savedList: vi.fn(), savedCreate: vi.fn(), history: vi.fn(),
}));
vi.mock("next/router", () => ({ useRouter: () => mocks.router }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => mocks.auth }));
vi.mock("@/lib/api/projects", () => ({ projectsApi: { listProjects: async () => ({ data: [] }), listAllProjects: async () => [{ id: "project", name: "Research" }] } }));
vi.mock("@/lib/api/documents", () => ({ documentsApi: { listDocuments: async () => ({ data: [{ id: "cached", source_type: "interview", uploaded_at: "2020-01-01" }], pagination: { total: 145 } }) } }));
vi.mock("@/lib/api/savedSearches", () => ({ savedSearchesApi: { list: mocks.savedList, execute: mocks.savedExecute, create: mocks.savedCreate } }));
vi.mock("@/lib/api/search", () => ({ searchApi: { history: mocks.history, pedrSearch: mocks.pedr, ragQuery: mocks.rag, semanticSearch: mocks.semantic, replay: mocks.replay, facets: async () => ({ source_types: [{ value: "report", label: "Report", count: 120 }] }) } }));
vi.mock("@/components/RagSynthesis", () => ({ RagSynthesis: ({ payload, error }: { payload?: { answer: string }; error?: string }) => <div>{payload?.answer}{error && <p>{error}</p>}</div> }));
vi.mock("@/components/PEDRMetadataPanel", () => ({ PEDRMetadataPanel: ({ metadata }: { metadata?: { query: string } }) => metadata ? <p>Ranking for {metadata.query}</p> : null }));
vi.mock("@/components/ResultCard", () => ({ ResultCard: ({ result }: { result: { chunk_id: string; content: string } }) => <article data-testid="search-result" data-chunk-id={result.chunk_id}>{result.content}</article> }));

import { SearchPage } from "@/features/search/SearchExperience";
import { HttpError } from "@/lib/api/http";

const chunk = (id: string, document_id = "uncached") => ({ chunk_id: id, document_id, content: `Finding ${id}`, score: 0.5, rrf_score: 0.5 });
const saved = { id: "saved-id", name: "Saved question", query_text: "saved question", top_k: 10, filters: { source_type: "report", date_from: "2026-01-01" }, use_count: 0, created_at: "2026-01-01", updated_at: "2026-01-01" };
const history = { id: "history-id", query_text: "history question", top_k: 10, filters: {}, created_at: "2026-01-01", result_count: 1 };
function search() { fireEvent.click(screen.getByRole("button", { name: "Search", exact: true })); }
function resultIds() { return screen.queryAllByTestId("search-result").map(node => node.getAttribute("data-chunk-id")); }

beforeEach(() => {
  mocks.router.query = {};
  mocks.auth.user.user_id = "alice";
  mocks.semantic.mockReset().mockResolvedValue({ results: [] });
  mocks.rag.mockReset().mockResolvedValue({ answer: "A sourced answer", citations: [] });
  mocks.history.mockReset().mockResolvedValue({ entries: [] });
  mocks.savedList.mockReset().mockResolvedValue({ items: [], limit_per_user: 50 });
  mocks.savedCreate.mockReset().mockResolvedValue(saved);
  mocks.savedExecute.mockReset().mockResolvedValue({ saved_search: saved, semantic: { results: [chunk("saved")] }, rag: { answer: "Saved answer" } });
  mocks.replay.mockReset().mockResolvedValue({ entry: history, semantic: { results: [chunk("history")] }, rag: { answer: "History answer" } });
  mocks.pedr.mockReset().mockResolvedValue({ results: [], metadata: null });
});
function searchPage() { return <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}><SearchPage /></SWRConfig>; }

describe("search commands from the shell", () => {
  it("runs a deep-linked query once and runs a new command without remounting the page", async () => {
    mocks.router.query = { q: " source provenance " };
    const view = await act(async () => render(searchPage()));
    await waitFor(() => expect(mocks.pedr).toHaveBeenCalledTimes(1));
    expect(mocks.pedr.mock.calls[0][0].query).toBe("source provenance");
    expect(screen.getByDisplayValue("source provenance")).toBeTruthy();
    view.rerender(searchPage());
    expect(mocks.pedr).toHaveBeenCalledTimes(1);
    mocks.router.query = { q: "contradicting evidence" };
    view.rerender(searchPage());
    await waitFor(() => expect(mocks.pedr).toHaveBeenCalledTimes(2));
    expect(mocks.pedr.mock.calls[1][0].query).toBe("contradicting evidence");
  });

  it("does not rerun the route query when the user edits the search field", async () => {
    mocks.router.query = { q: "first question" };
    await act(async () => { render(searchPage()); });
    await waitFor(() => expect(mocks.pedr).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByDisplayValue("first question"), { target: { value: "a draft question" } });
    expect(mocks.pedr).toHaveBeenCalledTimes(1);
    expect(screen.getByDisplayValue("a draft question")).toBeTruthy();
  });

  it.each(["   ", ["one", "two"]])("ignores empty or ambiguous route queries (%j)", async (q) => {
    mocks.router.query = { q };
    await act(async () => { render(searchPage()); });
    expect(mocks.pedr).not.toHaveBeenCalled();
  });
});

describe("API-authoritative search state", () => {
  it("sends source/date filters to both APIs and keeps exact results despite incomplete document metadata", async () => {
    mocks.pedr.mockResolvedValue({ results: [chunk("first", "cached"), chunk("second")], metadata: { query: "question" } });
    await act(async () => { render(searchPage()); });
    fireEvent.change(screen.getByRole("textbox", { name: "Search query" }), { target: { value: "question" } });
    fireEvent.change(await screen.findByLabelText("Source type"), { target: { value: "report" } });
    fireEvent.change(screen.getByLabelText("Collected from"), { target: { value: "2026-01-01" } });
    fireEvent.change(screen.getByLabelText("Collected until"), { target: { value: "2026-06-30" } });
    search();
    await waitFor(() => expect(resultIds()).toEqual(["first", "second"]));
    const filters = { source_type: "report", date_from: "2026-01-01", date_to: "2026-06-30" };
    expect(mocks.pedr).toHaveBeenCalledWith(expect.objectContaining(filters));
    expect(mocks.rag).toHaveBeenCalledWith(expect.objectContaining(filters));
    fireEvent.change(screen.getByLabelText("Source type"), { target: { value: "" } });
    expect(resultIds()).toEqual(["first", "second"]);
    expect(mocks.pedr).toHaveBeenCalledTimes(1);
  });

  it("keeps initial, empty and failed result states distinct", async () => {
    await act(async () => { render(searchPage()); });
    expect(screen.getByText("Start with a question")).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Search query" }), { target: { value: "nothing" } });
    search();
    expect(await screen.findByText("No matching results")).toBeTruthy();
    mocks.pedr.mockRejectedValue(new Error("Unavailable"));
    mocks.semantic.mockRejectedValue(new Error("Unavailable"));
    search();
    expect(await screen.findByText("Search unavailable")).toBeTruthy();
    expect(screen.queryByText("No matching results")).toBeNull();
  });

  it("ignores an older search and does not start its synthesis after a newer command", async () => {
    let release!: (value: unknown) => void;
    mocks.pedr.mockImplementation(({ query }) => query === "old" ? new Promise(resolve => { release = resolve; }) : Promise.resolve({ results: [chunk("new")], metadata: null }));
    mocks.router.query = { q: "old" };
    const view = await act(async () => render(searchPage()));
    await waitFor(() => expect(mocks.pedr).toHaveBeenCalledTimes(1));
    mocks.router.query = { q: "new" };
    view.rerender(searchPage());
    await waitFor(() => expect(resultIds()).toEqual(["new"]));
    await act(async () => release({ results: [chunk("old")], metadata: null }));
    expect(resultIds()).toEqual(["new"]);
    expect(mocks.rag).toHaveBeenCalledTimes(1);
    expect(mocks.rag).toHaveBeenCalledWith(expect.objectContaining({ query: "new" }));
  });

  it.each(["saved", "history"])("clears previous PEDR results and executes a %s route exactly once", async kind => {
    mocks.router.query = { q: "old" };
    mocks.pedr.mockResolvedValue({ results: [chunk("old")], metadata: { query: "old" } });
    const view = await act(async () => render(searchPage()));
    await waitFor(() => expect(resultIds()).toEqual(["old"]));
    mocks.router.query = { [kind]: `${kind}-id` };
    view.rerender(searchPage());
    await waitFor(() => expect(resultIds()).toEqual([kind]));
    expect(screen.queryByText("Ranking for old")).toBeNull();
    view.rerender(searchPage());
    expect(kind === "saved" ? mocks.savedExecute : mocks.replay).toHaveBeenCalledTimes(1);
    expect(mocks.pedr).toHaveBeenCalledTimes(1);
  });

  it("reports an inaccessible saved search as not found, without old result content", async () => {
    mocks.router.query = { saved: "missing" };
    mocks.savedExecute.mockRejectedValue(new HttpError("Not found", 404));
    await act(async () => { render(searchPage()); });
    expect(await screen.findByText("Search not found")).toBeTruthy();
    expect(resultIds()).toEqual([]);
    expect(screen.queryByText("No matching results")).toBeNull();
  });

  it("saves a query and its filters, then renders the saved-search execution response", async () => {
    mocks.savedCreate.mockImplementation(async payload => { mocks.savedList.mockResolvedValue({ items: [{ ...saved, ...payload }], limit_per_user: 50 }); return { ...saved, ...payload }; });
    await act(async () => { render(searchPage()); });
    fireEvent.change(screen.getByRole("textbox", { name: "Search query" }), { target: { value: "saved question" } });
    fireEvent.change(await screen.findByLabelText("Source type"), { target: { value: "report" } });
    fireEvent.change(screen.getByLabelText("Collected from"), { target: { value: "2026-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save current search" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Name", exact: true }), { target: { value: "Saved question" } });
    fireEvent.click(screen.getByRole("button", { name: "Save search", exact: true }));
    expect(await screen.findByRole("button", { name: "Run now" })).toBeTruthy();
    expect(mocks.savedCreate).toHaveBeenCalledWith(expect.objectContaining({ query_text: "saved question", filters: saved.filters }));
    fireEvent.click(screen.getByRole("button", { name: "Run now" }));
    await waitFor(() => expect(resultIds()).toEqual(["saved"]));
    expect(screen.getByText("Saved answer")).toBeTruthy();
  });

  it("does not carry result data into another account", async () => {
    mocks.router.query = { q: "private" };
    mocks.pedr.mockResolvedValue({ results: [chunk("alice-only")], metadata: null });
    const view = await act(async () => render(searchPage()));
    await waitFor(() => expect(resultIds()).toEqual(["alice-only"]));
    mocks.auth.user.user_id = "bob";
    mocks.router.query = {};
    view.rerender(searchPage());
    expect(resultIds()).toEqual([]);
    expect(screen.queryByText("A sourced answer")).toBeNull();
  });

  it("does not let an older synthesis overwrite a newer answer", async () => {
    let release!: (value: unknown) => void;
    mocks.pedr.mockImplementation(async ({ query }) => ({ results: [chunk(query)], metadata: null }));
    mocks.rag.mockImplementation(({ query }) => query === "old" ? new Promise(resolve => { release = resolve; }) : Promise.resolve({ answer: "New answer" }));
    mocks.router.query = { q: "old" };
    const view = await act(async () => render(searchPage()));
    await waitFor(() => expect(mocks.rag).toHaveBeenCalledTimes(1));
    mocks.router.query = { q: "new" };
    view.rerender(searchPage());
    expect(await screen.findByText("New answer")).toBeTruthy();
    await act(async () => release({ answer: "Old answer" }));
    expect(screen.queryByText("Old answer")).toBeNull();
    expect(resultIds()).toEqual(["new"]);
  });

  it("retains source results when only synthesis fails", async () => {
    mocks.router.query = { q: "question" };
    mocks.pedr.mockResolvedValue({ results: [chunk("source")], metadata: null });
    mocks.rag.mockRejectedValue(new Error("Synthesis unavailable"));
    await act(async () => { render(searchPage()); });
    expect(await screen.findByText("Synthesis is unavailable. The search results are still available above.")).toBeTruthy();
    expect(resultIds()).toEqual(["source"]);
    expect(screen.queryByText("Search unavailable")).toBeNull();
  });

  it("keeps the same filters in semantic fallback and never sends blank filter strings", async () => {
    mocks.pedr.mockRejectedValue(new Error("PEDR unavailable"));
    mocks.semantic.mockResolvedValue({ results: [chunk("fallback")] });
    await act(async () => { render(searchPage()); });
    fireEvent.change(screen.getByRole("textbox", { name: "Search query" }), { target: { value: "question" } });
    fireEvent.change(screen.getByLabelText("Collected from"), { target: { value: "2026-01-01" } });
    search();
    expect(await screen.findByText("A sourced answer")).toBeTruthy();
    expect(resultIds()).toEqual(["fallback"]);
    const request = mocks.semantic.mock.calls[0][0];
    expect(request.date_from).toBe("2026-01-01");
    expect(JSON.parse(JSON.stringify(request))).toEqual({ query: "question", top_k: 10, date_from: "2026-01-01" });
    expect(mocks.rag).toHaveBeenCalledWith(request);
  });
});
