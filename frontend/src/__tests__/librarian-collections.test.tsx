import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";

import { CollectionOrigin, CollectionSuggestions } from "@/components/librarian/CollectionSuggestions";
import { organisationApi, type AcceptedCollection, type CollectionSuggestions as Suggestions } from "@/lib/api/librarian-collections";

vi.mock("@/lib/api/librarian-collections", () => ({ organisationApi: { draft: vi.fn(), accept: vi.fn(), provenance: vi.fn() } }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => <a href={href} {...props}>{children}</a> }));

const destination = { owner_id: "alice", workspace_id: "space", space_name: "Default Workspace" };
const proposal: Suggestions = {
  project_id: "project", prompt: "Group feedback", model: "model", destination,
  coverage: { readable_documents: 10, documents_with_eligible_chunks: 8, used_documents: 2, readable_chunks: 50, eligible_chunks: 48, used_chunks: 20, excluded_chunks: 2, limited: true, chunk_limit: 20, character_limit: 24000 },
  groups: [
    { group_id: "one", proposal_token: "signed-one", name: "Navigation", description: "Review navigation", rationale: "Source navigation [2] [1].", members: [
      { marker: 2, available: true, chunk_id: "b", document_name: "Interview B", excerpt: "Finding B", href: "/documents/doc-b?chunk=b&index=0" },
      { marker: 1, available: true, chunk_id: "a", document_name: "Interview A", excerpt: "Finding A", href: "/documents/doc-a?chunk=a&index=0" },
    ] },
    { group_id: "two", proposal_token: "signed-two", name: "Trust", description: "Review confidence", rationale: "Traceable sources [1].", members: [
      { marker: 1, available: true, chunk_id: "a", document_name: "Interview A", excerpt: "Finding A", href: "/documents/doc-a?chunk=a&index=0" },
    ] },
  ],
};
const saved: AcceptedCollection = { collection_id: "one", name: "Navigation", href: "/collections/one", state: "saved", completed_member_ids: ["b", "a"], missing_member_ids: [], destination };
function panel(userId = "alice", projectId = "project") {
  return <CollectionSuggestions key={`${userId}:${projectId}`} userId={userId} projectId={projectId} projectName="Onboarding" />;
}
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear();
  vi.mocked(organisationApi.draft).mockResolvedValue(proposal);
  vi.mocked(organisationApi.accept).mockResolvedValue(saved);
});
async function draft() {
  fireEvent.change(screen.getByLabelText("How should the research be organised?"), { target: { value: proposal.prompt } });
  fireEvent.click(screen.getByRole("button", { name: "Suggest collections" }));
  await screen.findByRole("region", { name: "Review suggested collections" });
}
const group = (n: number) => within(screen.getByRole("article", { name: `Suggested collection ${n}` }));

it("generates only on request and preserves review edits without saving on navigation or dismissal", async () => {
  const view = render(panel());
  expect(organisationApi.draft).not.toHaveBeenCalled();
  await draft();
  fireEvent.change(screen.getByLabelText("Collection name 1"), { target: { value: "My grouping" } });
  view.unmount(); render(panel());
  expect(await screen.findByLabelText("Collection name 1")).toHaveValue("My grouping");
  expect(organisationApi.draft).toHaveBeenCalledTimes(1);
  fireEvent.click(group(1).getByRole("button", { name: "Dismiss group" }));
  expect(screen.queryByLabelText("Collection name 1")).toBeNull();
  expect(screen.getByLabelText("Collection name 2")).toHaveValue("Trust");
  expect(organisationApi.accept).not.toHaveBeenCalled();
});

it("accepts only the edited group and selected subset with no second model call", async () => {
  vi.mocked(organisationApi.accept).mockResolvedValue({ ...saved, name: "Reviewed", completed_member_ids: ["a"] });
  render(panel()); await draft();
  fireEvent.change(screen.getByLabelText("Collection name 1"), { target: { value: "Reviewed" } });
  fireEvent.change(screen.getByLabelText("Collection description 1"), { target: { value: "Human purpose" } });
  fireEvent.click(screen.getByRole("checkbox", { name: "Include excerpt 2 in collection 1" }));
  fireEvent.click(group(1).getByRole("button", { name: "Accept this collection" }));
  expect(await screen.findByRole("link", { name: "Reviewed" })).toHaveAttribute("href", "/collections/one");
  expect(organisationApi.accept).toHaveBeenCalledExactlyOnceWith("project", "signed-one", "Reviewed", "Human purpose", ["a"]);
  expect(group(2).getByRole("button", { name: "Accept this collection" })).toBeEnabled();
  fireEvent.click(group(2).getByRole("button", { name: "Dismiss group" }));
  expect(organisationApi.accept).toHaveBeenCalledTimes(1);
  expect(organisationApi.draft).toHaveBeenCalledTimes(1);
});

it("retries a persisted partial result using the same frozen proposal and order", async () => {
  vi.mocked(organisationApi.accept).mockResolvedValueOnce({ ...saved, state: "partial", completed_member_ids: ["b"], missing_member_ids: ["a"] }).mockResolvedValueOnce(saved);
  const view = render(panel()); await draft();
  fireEvent.click(group(1).getByRole("button", { name: "Accept this collection" }));
  await screen.findByRole("button", { name: "Retry 1 missing excerpts" });
  expect(screen.getByLabelText("Collection name 1")).toBeDisabled();
  view.unmount(); render(panel());
  fireEvent.click(await screen.findByRole("button", { name: "Retry 1 missing excerpts" }));
  await screen.findByText("Reviewed collection saved.");
  expect(organisationApi.accept).toHaveBeenNthCalledWith(1, "project", "signed-one", "Navigation", "Review navigation", ["b", "a"]);
  expect(organisationApi.accept).toHaveBeenNthCalledWith(2, "project", "signed-one", "Navigation", "Review navigation", ["b", "a"]);
  expect(organisationApi.draft).toHaveBeenCalledTimes(1);
});

it("discloses sampled excerpt coverage, destination ownership and exact source links", async () => {
  render(panel()); await draft();
  expect(screen.getByText(/Destination: Default Workspace/)).toHaveTextContent("Owned by you");
  expect(screen.getByText(/Read 20 of 50/)).toHaveTextContent("2 documents have no eligible excerpts");
  expect(screen.getByText(/Read 20 of 50/)).toHaveTextContent("partial sample");
  expect(group(1).getByRole("link", { name: "Open excerpt [2]" })).toHaveAttribute("href", "/documents/doc-b?chunk=b&index=0");
  expect(screen.getByRole("region", { name: "Review suggested collections" })).toHaveFocus();
});

it("isolates account/project state and ignores a late result after switching", async () => {
  const view = render(panel()); await draft();
  view.rerender(panel("bob"));
  expect(screen.queryByLabelText("Collection name 1")).toBeNull();
  view.rerender(panel("alice", "other"));
  expect(screen.queryByLabelText("Collection name 1")).toBeNull();
  view.rerender(panel());
  expect(await screen.findByLabelText("Collection name 1")).toHaveValue("Navigation");
  let resolve!: (value: Suggestions) => void;
  vi.mocked(organisationApi.draft).mockReturnValue(new Promise(done => { resolve = done; }));
  fireEvent.click(screen.getByRole("button", { name: "Suggest groups again" }));
  view.rerender(panel("bob"));
  await act(async () => { resolve(proposal); });
  expect(screen.queryByLabelText("Collection name 1")).toBeNull();
  expect(localStorage.getItem("tracelab.librarian.collections.v1:bob:project")).toBeNull();
});

it("shows a stale acceptance failure without regenerating or losing reviewed edits", async () => {
  vi.mocked(organisationApi.accept).mockRejectedValue(new Error("The source changed. Review again."));
  render(panel()); await draft();
  fireEvent.click(group(1).getByRole("button", { name: "Accept this collection" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("source changed");
  expect(screen.getByLabelText("Collection name 1")).toHaveValue("Navigation");
  expect(organisationApi.draft).toHaveBeenCalledTimes(1);
});

it("prevents empty membership and concurrent button presses", async () => {
  let resolve!: (value: AcceptedCollection) => void;
  vi.mocked(organisationApi.accept).mockReturnValue(new Promise(done => { resolve = done; }));
  render(panel()); await draft();
  for (const checkbox of group(1).getAllByRole("checkbox")) fireEvent.click(checkbox);
  expect(group(1).getByRole("button", { name: "Accept this collection" })).toBeDisabled();
  fireEvent.click(group(1).getAllByRole("checkbox")[0]);
  const accept = group(1).getByRole("button", { name: "Accept this collection" });
  fireEvent.click(accept); fireEvent.click(accept);
  expect(organisationApi.accept).toHaveBeenCalledTimes(1);
  await act(async () => { resolve({ ...saved, completed_member_ids: ["b"] }); });
});

it("reopens provenance without fabricating links for unavailable sources", async () => {
  vi.mocked(organisationApi.provenance).mockResolvedValue({ provenance: {
    origin: "librarian", model: "model", accepted_by: "alice", accepted_at: "2026-09-29T00:00:00Z", completed_at: "2026-09-29T00:00:00Z", destination, prompt: "Group feedback",
    members: [{ marker: 2, available: true, excerpt: "Finding B", href: "/documents/doc-b?chunk=b&index=0" }, { marker: 1, available: false }],
  } });
  render(<SWRConfig value={{ provider: () => new Map() }}><CollectionOrigin userId="alice" collectionId="one" /></SWRConfig>);
  await screen.findByRole("heading", { name: "Machine suggested · Human accepted" });
  fireEvent.click(screen.getByText("Originally accepted sources"));
  expect(screen.getByRole("link", { name: "[2] Finding B" })).toHaveAttribute("href", "/documents/doc-b?chunk=b&index=0");
  expect(screen.getByText("[1] Source no longer available")).toBeVisible();
  expect(screen.queryByRole("link", { name: /\[1\]/ })).toBeNull();
  await waitFor(() => expect(organisationApi.draft).not.toHaveBeenCalled());
});
