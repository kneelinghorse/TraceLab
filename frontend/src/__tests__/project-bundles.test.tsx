import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
import type { ReactNode } from "react";

const mocks = vi.hoisted(() => ({ documents: vi.fn(), evidence: vi.fn(), collections: vi.fn(), missions: vi.fn(), reports: vi.fn(), favorites: vi.fn(), pin: vi.fn(), unpin: vi.fn(), user: "reader-a" }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { user_id: mocks.user } }) }));
vi.mock("@/lib/api/documents", () => ({ documentsApi: { listDocuments: mocks.documents } }));
vi.mock("@/lib/api/evidence", () => ({ evidenceApi: { list: mocks.evidence } }));
vi.mock("@/lib/api/collections", () => ({ collectionsApi: { list: mocks.collections } }));
vi.mock("@/lib/api/missions", () => ({ missionsApi: { list: mocks.missions } }));
vi.mock("@/lib/api/reports", () => ({ reportsApi: { list: mocks.reports } }));
vi.mock("@/lib/api/home", () => ({ homeApi: { favorites: mocks.favorites, pinProject: mocks.pin, unpinProject: mocks.unpin } }));
vi.mock("@/components/evidence/EntryCard", () => ({ EntryCard: ({ entry }: { entry: { claim: string } }) => <p>{entry.claim}</p> }));
import { ProjectResources } from "@/components/projects/ProjectResources";
import { ProjectFavorite } from "@/components/projects/ProjectFavorite";
import { FavoriteProjects } from "@/components/projects/FavoriteProjects";

function wrapper({ children }: { children: ReactNode }) { return <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}>{children}</SWRConfig>; }
beforeEach(() => { vi.clearAllMocks(); mocks.user = "reader-a"; mocks.favorites.mockResolvedValue({ total: 0, items: [] }); });

describe("project bundle resources", () => {
  it("pages documents using the full server total and current project", async () => {
    mocks.documents.mockImplementation(({ page }: { page: number }) => Promise.resolve({ pagination: { total: 123 }, data: [{ id: String(page), project_id: "project", name: `Source page ${page}`, processed: false, chunked: false, embedded: false }] }));
    render(<ProjectResources projectId="project" tab="Documents" refreshStats={vi.fn()} onBusyChange={vi.fn()} />, { wrapper });
    expect(await screen.findByText("123 documents")).toBeVisible();
    fireEvent.click(within(screen.getByRole("navigation", { name: "Project documents pages" })).getByRole("button", { name: "Next" }));
    expect(await screen.findByRole("link", { name: "Source page 2" })).toBeVisible();
    expect(mocks.documents).toHaveBeenLastCalledWith({ projectId: "project", page: 2, pageSize: 20 });
  });
  it.each(["Evidence", "Collections", "Missions", "Reports"] as const)("gets %s from its scoped paginated endpoint", async tab => {
    mocks.evidence.mockResolvedValue({ entry_total: 43, entries: [{ id: "e", claim: "Traceable evidence" }] });
    mocks.collections.mockResolvedValue({ total: 43, data: [{ id: "c", name: "Context", description: null }] });
    mocks.missions.mockResolvedValue({ pagination: { total: 43 }, data: [{ id: "m", title: "Research", objective: "Audit", status: "completed" }] });
    mocks.reports.mockResolvedValue({ total: 43, items: [{ id: "r", title: "Results", status: "final" }] });
    render(<ProjectResources projectId="project" tab={tab} refreshStats={vi.fn()} onBusyChange={vi.fn()} />, { wrapper });
    expect(await screen.findByText(`43 ${tab.toLowerCase()}`)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    const api = { Evidence: mocks.evidence, Collections: mocks.collections, Missions: mocks.missions, Reports: mocks.reports }[tab];
    await waitFor(() => expect(api).toHaveBeenCalledTimes(2));
    if (tab === "Evidence") expect(api).toHaveBeenLastCalledWith("project", 2);
    else expect(api).toHaveBeenLastCalledWith(expect.objectContaining({ project_id: "project", page: 2, page_size: 20 }));
  });
  it("distinguishes inaccessible resource failures from an empty project tab", async () => {
    mocks.reports.mockRejectedValueOnce(new Error("unavailable")).mockResolvedValueOnce({ total: 0, items: [] });
    render(<ProjectResources projectId="project" tab="Reports" refreshStats={vi.fn()} onBusyChange={vi.fn()} />, { wrapper });
    expect(await screen.findByRole("alert")).toHaveTextContent("Reports could not load");
    expect(screen.queryByText("No accessible reports in this project.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No accessible reports in this project.")).toBeVisible();
  });
});

describe("personal project shortcuts", () => {
  it("waits for the saved server state and keeps a failed pin visibly unpinned", async () => {
    mocks.pin.mockRejectedValueOnce(new Error("offline"));
    render(<ProjectFavorite projectId="project" />, { wrapper });
    const pin = await screen.findByRole("button", { name: "Favorite project" });
    await waitFor(() => expect(pin).not.toBeDisabled());
    fireEvent.click(pin);
    expect(await screen.findByRole("alert")).toHaveTextContent("Favorite could not be saved");
    expect(screen.getByRole("button", { name: "Favorite project" })).toHaveAttribute("aria-pressed", "false");
    mocks.pin.mockResolvedValueOnce(undefined);
    mocks.favorites.mockResolvedValueOnce({ total: 1, items: [] });
    fireEvent.click(screen.getByRole("button", { name: "Favorite project" }));
    expect(await screen.findByRole("button", { name: "Unfavorite project" })).toHaveAttribute("aria-pressed", "true");
  });
  it("never carries one user's favorite state into the next user's SWR scope", async () => {
    mocks.favorites.mockResolvedValueOnce({ total: 1, items: [] }).mockResolvedValue({ total: 0, items: [] });
    const view = render(<ProjectFavorite projectId="project" />, { wrapper });
    expect(await screen.findByRole("button", { name: "Unfavorite project" })).toBeVisible();
    mocks.user = "reader-b";
    view.rerender(<ProjectFavorite projectId="project" />);
    expect(await screen.findByRole("button", { name: "Favorite project" })).toHaveAttribute("aria-pressed", "false");
  });
  it("shows Home's exact favorite total and can reach favorites beyond its bounded first six", async () => {
    mocks.favorites.mockResolvedValue({ total: 7, items: [{ id: "last", title: "Seventh project", href: "/projects/last" }] });
    render(<FavoriteProjects initial={{ total: 7, items: [{ id: "first", title: "First project", href: "/projects/first", updated_at: null }] }} />, { wrapper });
    expect(screen.getByRole("heading", { name: "Favorite projects (7)" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByRole("link", { name: "Seventh project" })).toHaveAttribute("href", "/projects/last");
    expect(mocks.favorites).toHaveBeenCalledWith({ page: 2 });
  });
});
