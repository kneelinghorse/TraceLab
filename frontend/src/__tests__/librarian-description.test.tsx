import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";

import { ProjectDescription } from "@/components/librarian/ProjectDescription";
import { descriptionApi, type DescriptionProposal, type DescriptionState } from "@/lib/api/librarian-descriptions";

vi.mock("@/lib/api/librarian-descriptions", () => ({ descriptionApi: { state: vi.fn(), draft: vi.fn(), accept: vi.fn(), restore: vi.fn() } }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => <a href={href} {...props}>{children}</a> }));

const initial: DescriptionState = { project_id: "project", description: "Human original", revision: 0, provenance: null, can_restore: false };
const proposal: DescriptionProposal = { project_id: "project", proposal_token: "signed-fixture", description: "Planned onboarding research.", current_description: initial.description, prompt: "Plan onboarding", model: "model", basis: "planning_brief", citations: [], coverage: { readable_chunks: 0, eligible_chunks: 0, used_chunks: 0, excluded_chunks: 0, limited: false, chunk_limit: 12, character_limit: 24000 } };
function panel(userId = "alice", projectId = "project") {
  return <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}><ProjectDescription key={`${userId}:${projectId}`} userId={userId} projectId={projectId} projectName="Onboarding" /></SWRConfig>;
}
beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  vi.mocked(descriptionApi.state).mockResolvedValue(initial);
  vi.mocked(descriptionApi.draft).mockResolvedValue(proposal);
});
async function draft() {
  await screen.findByText("Human original");
  fireEvent.change(screen.getByLabelText("What should the description explain?"), { target: { value: proposal.prompt } });
  fireEvent.click(screen.getByRole("button", { name: "Draft description" }));
  await screen.findByRole("region", { name: "Review description" });
}

it("drafts only on request, preserves edits across navigation, and dismissal never accepts", async () => {
  const first = render(panel());
  await screen.findByText("Human original");
  expect(descriptionApi.draft).not.toHaveBeenCalled();
  await draft();
  fireEvent.change(screen.getByLabelText("Proposed description (editable)"), { target: { value: "My reviewed text" } });
  first.unmount();
  render(panel());
  expect(await screen.findByLabelText("Proposed description (editable)")).toHaveValue("My reviewed text");
  expect(descriptionApi.draft).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Dismiss draft" }));
  await waitFor(() => expect(screen.queryByLabelText("Proposed description (editable)")).toBeNull());
  expect(descriptionApi.accept).not.toHaveBeenCalled();
  expect(descriptionApi.restore).not.toHaveBeenCalled();
  expect(localStorage.getItem("tracelab.librarian.description.v1:alice:project")).toBeNull();
});

it("binds acceptance to the reviewed proposal and edits, then shows provenance and guarded restore", async () => {
  const accepted: DescriptionState = { ...initial, description: "Reviewed plan", revision: 1, can_restore: true, provenance: {
    proposal_id: "proposal", current: true, origin: "librarian", model: "model", prompt: proposal.prompt, basis: "planning_brief", accepted_by: "alice", accepted_at: "2026-09-29T00:00:00Z", previous_value: initial.description, accepted_value: "Reviewed plan", generated_value: proposal.description, edited: true, restored_at: null, citations: [],
  } };
  vi.mocked(descriptionApi.accept).mockResolvedValue(accepted);
  vi.mocked(descriptionApi.restore).mockResolvedValue({ ...initial, revision: 2 });
  render(panel());
  await draft();
  fireEvent.change(screen.getByLabelText("Proposed description (editable)"), { target: { value: "Reviewed plan" } });
  fireEvent.click(screen.getByRole("button", { name: "Accept description" }));
  expect(await screen.findByText(/Machine drafted · Human accepted with edits/)).toBeVisible();
  expect(descriptionApi.accept).toHaveBeenCalledWith("project", proposal.proposal_token, "Reviewed plan");
  expect(descriptionApi.draft).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Restore previous description" }));
  await screen.findByText("Previous description restored.");
  expect(descriptionApi.restore).toHaveBeenCalledWith("project", "proposal");
});

it("isolates stored proposals by account and project", async () => {
  const view = render(panel());
  await draft();
  view.rerender(panel("bob"));
  await screen.findByText("Human original");
  expect(screen.queryByLabelText("Proposed description (editable)")).toBeNull();
  view.rerender(panel("alice", "other"));
  await screen.findByText("Human original");
  expect(screen.queryByLabelText("Proposed description (editable)")).toBeNull();
  view.rerender(panel());
  expect(await screen.findByLabelText("Proposed description (editable)")).toHaveValue(proposal.description);
});

it("does not put a late paid reply into a switched account", async () => {
  let resolve!: (value: DescriptionProposal) => void;
  vi.mocked(descriptionApi.draft).mockReturnValue(new Promise((done) => { resolve = done; }));
  const view = render(panel());
  await screen.findByText("Human original");
  fireEvent.change(screen.getByLabelText("What should the description explain?"), { target: { value: "Plan research" } });
  fireEvent.click(screen.getByRole("button", { name: "Draft description" }));
  view.rerender(panel("bob"));
  await act(async () => { resolve(proposal); });
  expect(screen.queryByLabelText("Proposed description (editable)")).toBeNull();
  expect(localStorage.getItem("tracelab.librarian.description.v1:bob:project")).toBeNull();
});

it("reports acceptance conflicts without discarding the review or regenerating", async () => {
  vi.mocked(descriptionApi.accept).mockRejectedValue(new Error("The description changed since this draft."));
  render(panel());
  await draft();
  fireEvent.click(screen.getByRole("button", { name: "Accept description" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("description changed");
  expect(screen.getByLabelText("Proposed description (editable)")).toHaveValue(proposal.description);
  expect(descriptionApi.draft).toHaveBeenCalledTimes(1);
});

it("renders bounded corpus coverage and resolving sources", async () => {
  vi.mocked(descriptionApi.draft).mockResolvedValue({ ...proposal, basis: "corpus", description: "Finding [1].", citations: [{ marker: 1, available: true, href: "/documents/doc?chunk=c&index=0", excerpt: "Source excerpt" }], coverage: { ...proposal.coverage, used_chunks: 6, readable_chunks: 22, eligible_chunks: 20, excluded_chunks: 2, limited: true } });
  render(panel());
  await draft();
  expect(screen.getByText(/Based on 6 of 22/)).toHaveTextContent("2 empty or overlong chunks excluded");
  expect(screen.getByRole("link", { name: "[1] Source excerpt" })).toHaveAttribute("href", "/documents/doc?chunk=c&index=0");
});
