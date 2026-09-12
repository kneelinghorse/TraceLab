import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";

const mocks = vi.hoisted(() => ({
  router: { isReady: true, query: {} as { q?: string | string[] } },
  pedr: vi.fn(),
}));
vi.mock("next/router", () => ({ useRouter: () => mocks.router }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isReady: true, isAuthenticated: true }) }));
vi.mock("@/lib/api/projects", () => ({ projectsApi: { listProjects: async () => ({ data: [] }) } }));
vi.mock("@/lib/api/documents", () => ({ documentsApi: { listDocuments: async () => ({ data: [] }) } }));
vi.mock("@/lib/api/savedSearches", () => ({ savedSearchesApi: { list: async () => ({ items: [] }) } }));
vi.mock("@/lib/api/search", () => ({ searchApi: { history: async () => ({ entries: [] }), pedrSearch: mocks.pedr, ragQuery: async () => ({ answer: "A sourced answer", citations: [] }) } }));
vi.mock("@/components/RagSynthesis", () => ({ RagSynthesis: () => null }));

import { SearchPage } from "@/features/search/SearchExperience";

beforeEach(() => {
  mocks.router.query = {};
  mocks.pedr.mockReset().mockResolvedValue({ results: [], metadata: null });
});
function searchPage() { return <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}><SearchPage /></SWRConfig>; }

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
