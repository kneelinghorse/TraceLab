import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
import type { ReactNode } from "react";
const mocks = vi.hoisted(() => ({ documents: vi.fn(), removeDocument: vi.fn(), getDocument: vi.fn(), projects: vi.fn(), collections: vi.fn(), getCollection: vi.fn(), reports: vi.fn(), preview: vi.fn(), approve: vi.fn(), router: { isReady: true, query: {} as Record<string,string>, push: vi.fn() } }));
vi.mock("next/router", () => ({ useRouter: () => mocks.router }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isReady: true, isAuthenticated: true, user: { user_id: "reviewer" } }) }));
vi.mock("@/lib/api/documents", () => ({ documentsApi: { listDocuments: mocks.documents, deleteDocument: mocks.removeDocument, getDocument: mocks.getDocument, getDocumentChunks: vi.fn().mockResolvedValue({ data: [], pagination: { pages: 1 } }) } }));
vi.mock("@/lib/api/projects", () => ({ projectsApi: { listProjects: mocks.projects, listAllProjects: async () => (await mocks.projects()).data } }));
vi.mock("@/lib/api/collections", () => ({ collectionsApi: { list: mocks.collections, get: mocks.getCollection } }));
vi.mock("@/lib/api/reports", () => ({ reportsApi: { list: mocks.reports } }));
vi.mock("@/lib/api/deviceAuth", async original => ({ ...await original<typeof import("@/lib/api/deviceAuth")>(), previewDeviceGrant: mocks.preview, approveDeviceGrant: mocks.approve }));
import DocumentsPage from "@/pages/documents";
import DocumentPage from "@/pages/documents/[id]";
import CollectionsPage from "@/pages/collections";
import CollectionPage from "@/pages/collections/[id]";
import ReportsPage from "@/pages/reports";
import DevicePage from "@/pages/device";
import { useFeedback } from "@/components/ui/useFeedback";
import { HttpError } from "@/lib/api/http";
const doc = { id: "doc", name: "Auditable research", project_id: "project", processed: true, chunked: false, embedded: false, uploaded_at: "2026-09-13T00:00:00Z", file_type: "txt" };
beforeEach(() => {
  vi.clearAllMocks(); mocks.router.query = {}; mocks.router.isReady = true;
  mocks.documents.mockReset().mockResolvedValue({ data: [doc], pagination: { page: 1, pages: 3, total: 25 } });
  mocks.projects.mockReset().mockResolvedValue({ data: [{ id: "project", name: "Project" }], pagination: { page: 1, pages: 1, total: 1 } });
  mocks.collections.mockReset().mockResolvedValue({ data: [], total: 0 });
  mocks.getCollection.mockReset(); mocks.getDocument.mockReset(); mocks.removeDocument.mockReset();
  mocks.reports.mockReset().mockResolvedValue({ items: [], total: 0 });
  mocks.preview.mockReset(); mocks.approve.mockReset();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
async function browser(component: ReactNode) { let rendered: ReturnType<typeof render>; await act(async () => { rendered = render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}>{component}</SWRConfig>); }); return rendered!; }
describe("shared feedback and page state", () => {
  it("requires explicit acceptance before deletion, preserves failure, and retries through the same confirmation", async () => {
    mocks.removeDocument.mockRejectedValueOnce(new Error('{"detail":"Deletion unavailable"}')).mockResolvedValueOnce(undefined);
    await browser(<DocumentsPage />); await screen.findByText(doc.name);
    fireEvent.click(screen.getByRole("button", { name: "Delete Auditable research", exact: true }));
    let modal = within(screen.getByRole("dialog", { name: "Confirm action" }));
    fireEvent.click(modal.getByRole("button", { name: "Cancel" }));
    expect(mocks.removeDocument).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Delete Auditable research", exact: true }));
    modal = within(screen.getByRole("dialog", { name: "Confirm action" }));
    fireEvent.click(modal.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Deletion unavailable");
    expect(mocks.removeDocument).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Dismiss notification" }));
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Delete Auditable research", exact: true }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(mocks.removeDocument).toHaveBeenCalledTimes(2));
  });
  it("cancels an outstanding confirmation on unmount without performing a write", async () => {
    const write = vi.fn(); const decision = vi.fn();
    function Example() { const { feedback, askConfirmation } = useFeedback(); return <>{feedback}<button onClick={async () => { const accepted = await askConfirmation("Delete record?"); decision(accepted); if (accepted) write(); }}>Delete record</button></>; }
    const view = await browser(<Example />);
    fireEvent.click(screen.getByRole("button", { name: "Delete record" }));
    view.unmount();
    await waitFor(() => expect(decision).toHaveBeenCalledWith(false)); expect(write).not.toHaveBeenCalled();
  });
  it("resets paging in the filter event so a new filter never requests the old page", async () => {
    await browser(<DocumentsPage />); await screen.findByText(doc.name);
    fireEvent.click(screen.getByRole("button", { name: "Next", exact: true }));
    await waitFor(() => expect(mocks.documents).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })));
    mocks.documents.mockClear();
    fireEvent.change(screen.getByRole("searchbox", { name: "Search documents" }), { target: { value: "specific" } });
    await waitFor(() => expect(mocks.documents).toHaveBeenCalledWith(expect.objectContaining({ page: 1, search: "specific" })));
    expect(mocks.documents.mock.calls.every(([params]) => params.page === 1)).toBe(true);
  });
  it.each(["documents", "collections", "reports"])("failed %s reads show retry instead of a false empty state", async kind => {
    const api = { documents: mocks.documents, collections: mocks.collections, reports: mocks.reports }[kind]!;
    api.mockRejectedValueOnce(new Error("Unavailable"));
    await browser(kind === "documents" ? <DocumentsPage /> : kind === "collections" ? <CollectionsPage /> : <ReportsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("could not load");
    expect(screen.queryByText(/No (documents found|collections yet|reports yet)/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });
  it.each(["document", "collection"])("distinguishes a missing %s from an unresolved read", async kind => {
    mocks.router.query = { id: "missing" };
    const api = kind === "document" ? mocks.getDocument : mocks.getCollection;
    let reject!: (reason: Error) => void;
    api.mockImplementation(() => new Promise((_resolve, rejectPromise) => { reject = rejectPromise; }));
    await browser(kind === "document" ? <DocumentPage /> : <CollectionPage />);
    expect(screen.getByRole("status")).toHaveTextContent(/Loading/);
    await act(async () => reject(new HttpError("Not found", 404)));
    expect(await screen.findByText(new RegExp(kind + " not found", "i"))).toBeVisible();
    expect(screen.queryByText(/Loading/)).toBeNull();
  });
  it("requests each server collection page without hiding its scoped total", async () => {
    const rows = Array.from({length:25},(_,i)=>({ id:String(i), name:"Collection " + (i+1), item_count:0, created_at:"2026-09-13T00:00:00Z", updated_at:"2026-09-13T00:00:00Z" }));
    mocks.collections.mockImplementation(({page, page_size}) => Promise.resolve({ total: 25, data: rows.slice((page-1)*page_size, page*page_size) }));
    await browser(<CollectionsPage />);
    expect(await screen.findByText("Page 1 of 2 (25 total)")).toBeVisible();
    expect(screen.queryByRole("link", { name:"Collection 25", exact:true })).toBeNull();
    fireEvent.click(screen.getByRole("button", {name:"Next",exact:true}));
    expect(await screen.findByRole("link", {name:"Collection 25",exact:true})).toBeVisible();
    expect(mocks.collections).toHaveBeenLastCalledWith({ page: 2, page_size: 20 });
  });
  it("device deep links fetch a preview only; a click is required to approve", async () => {
    mocks.router.query = { code:"BCDF-GHJK" };
    mocks.preview.mockResolvedValue({ user_code:"BCDF-GHJK", client_label:"test-client", status:"pending", expires_at:"2099-09-13T00:00:00Z" });
    mocks.approve.mockResolvedValue({ label:"test-client" });
    await browser(<DevicePage />);
    expect(await screen.findByRole("button", {name:"Approve",exact:true})).toBeVisible();
    expect(mocks.preview).toHaveBeenCalledWith("BCDF-GHJK");
    expect(mocks.approve).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", {name:"Approve",exact:true}));
    await waitFor(() => expect(mocks.approve).toHaveBeenCalledWith("BCDF-GHJK", undefined));
  });
});
