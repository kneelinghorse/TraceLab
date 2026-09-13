import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
import { AddToCollection } from "@/components/AddToCollection";

const api = vi.hoisted(() => ({ list: vi.fn(), addDocument: vi.fn(), addChunk: vi.fn(), create: vi.fn() }));
vi.mock("@/lib/api/collections", () => ({ collectionsApi: api }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { user_id: "reader" } }) }));
const collection = { id: "context", name: "Research context", item_count: 0 };
function picker(props: React.ComponentProps<typeof AddToCollection>) {
  render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}><AddToCollection {...props} /></SWRConfig>);
}
beforeEach(() => {
  vi.resetAllMocks(); api.list.mockResolvedValue({ data: [collection], total: 121 });
  api.addDocument.mockResolvedValue({ id: "document" }); api.addChunk.mockResolvedValue({ id: "chunk" }); api.create.mockResolvedValue(collection);
});
it("adds a document without manufacturing a chunk and pages the complete collection total", async () => {
  const onAdded = vi.fn(); picker({ documentId: "document", onAdded });
  fireEvent.click(screen.getByRole("button", { name: "Add document to collection" }));
  expect(await screen.findByText("121 collections")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() => expect(api.list).toHaveBeenCalledWith({ page: 2, page_size: 20 }));
  fireEvent.click(screen.getByRole("button", { name: "Add to Research context" }));
  await waitFor(() => expect(api.addDocument).toHaveBeenCalledWith("context", "document"));
  expect(api.addChunk).not.toHaveBeenCalled(); expect(onAdded).toHaveBeenCalledOnce();
});
it("keeps a created collection when adding its first document fails", async () => {
  api.addDocument.mockRejectedValueOnce(new Error("Document could not be attached")); picker({ documentId: "document" });
  fireEvent.click(screen.getByRole("button", { name: "Add document to collection" }));
  await screen.findByText("121 collections");
  fireEvent.click(screen.getByText("Create a collection"));
  fireEvent.change(screen.getByLabelText("New collection name"), { target: { value: "Research context" } });
  fireEvent.click(screen.getByRole("button", { name: "Create and add" }));
  expect(await screen.findByText("Document could not be attached")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Retry adding to Research context" }));
  await waitFor(() => expect(api.addDocument).toHaveBeenCalledTimes(2));
  expect(api.create).toHaveBeenCalledTimes(1);
});
it("keeps excerpt callers on the existing chunk API and distinguishes collection load failure", async () => {
  api.list.mockRejectedValueOnce(new Error("offline")); picker({ chunkId: "chunk" });
  fireEvent.click(screen.getByRole("button", { name: "Add excerpt to collection" }));
  expect(await screen.findByText("Collections could not load.")).toBeVisible();
  expect(screen.queryByText("No collections available.")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  fireEvent.click(await screen.findByRole("button", { name: "Add to Research context" }));
  await waitFor(() => expect(api.addChunk).toHaveBeenCalledWith("context", { chunk_id: "chunk" }));
  expect(api.addDocument).not.toHaveBeenCalled();
});
