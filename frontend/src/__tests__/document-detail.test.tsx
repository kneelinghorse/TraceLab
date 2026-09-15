import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SWRConfig } from "swr";
import type { Document, DocumentContent } from "@/types/document";
import { isMarkdownDocument } from "@/lib/document-state";
const mocks = vi.hoisted(() => ({
  getDocument: vi.fn(), getContent: vi.fn(), listChunks: vi.fn(), processDocument: vi.fn(), deleteDocument: vi.fn(), downloadDocument: vi.fn(),
  push: vi.fn(), query: {} as Record<string, string | string[]>,
}));
vi.mock("@/lib/api/documents", () => ({ documentsApi: mocks }));
vi.mock("@/components/AuthGate", () => ({ AuthGate: ({ children }: { children: ReactNode }) => children }));
vi.mock("@/components/evidence/EvidencePanel", () => ({ EvidencePanel: () => <p>Linked evidence entries</p> }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { user_id: "reader" } }) }));
vi.mock("next/router", () => ({ useRouter: () => ({ query: mocks.query, push: mocks.push, isReady: true }) }));
import DocumentDetailPage from "@/pages/documents/[id]";

function document(overrides: Partial<Document> = {}): Document {
  return { id: "doc-1", project_id: "project-1", name: "interview.txt", mime_type: "text/plain", file_type: "transcript", file_size: 2048,
    processed: true, chunked: true, embedded: false, validation_status: "pending", chunk_count: 3, word_count: 1200, total_tokens: 1500,
    preview: "Only the first 500 characters…", source_origin: "upload", links: [], ...overrides };
}
function content(overrides: Partial<DocumentContent> = {}): DocumentContent {
  return { id: "doc-1", name: "interview.txt", mime_type: "text/plain", source_origin: "upload", content: "Full interview transcript body.", links: [], ...overrides };
}
function mount() { return render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}><DocumentDetailPage /></SWRConfig>); }
beforeEach(() => {
  vi.resetAllMocks(); mocks.query = { id: "doc-1" };
  mocks.getDocument.mockResolvedValue(document());
  mocks.getContent.mockResolvedValue(content());
  mocks.listChunks.mockResolvedValue({ data: [{ id: "chunk-1", document_id: "doc-1", chunk_index: 0, content: "Chunk body", token_count: 12, created_at: "2026-09-15T00:00:00" }], pagination: { total: 1, pages: 1, page: 1, page_size: 10 } });
});

it("opens on the Text tab and shows the full text from the content endpoint, not the preview", async () => {
  mount();
  expect(await screen.findByRole("heading", { name: "interview.txt" })).toBeVisible();
  expect(screen.getByRole("tab", { name: "Text" })).toHaveAttribute("aria-selected", "true");
  expect(await screen.findByText("Full interview transcript body.")).toBeVisible();
  expect(mocks.getContent).toHaveBeenCalledWith("doc-1");
  expect(screen.queryByText("Only the first 500 characters…")).toBeNull();
  expect(screen.queryByText("Processing Status")).toBeNull();
  expect(mocks.listChunks).not.toHaveBeenCalled();
});

it("renders markdown documents as markdown and plain text verbatim", async () => {
  mocks.getDocument.mockResolvedValue(document({ name: "synthesis.md", mime_type: "text/markdown", source_origin: "synthesized" }));
  mocks.getContent.mockResolvedValue(content({ name: "synthesis.md", mime_type: "text/markdown", source_origin: "synthesized", content: "# Key findings\n\n- One" }));
  const view = mount();
  expect(await screen.findByRole("heading", { level: 1, name: "Key findings" })).toBeVisible();
  expect(screen.getByRole("listitem")).toHaveTextContent("One");
  view.unmount();

  mocks.getDocument.mockResolvedValue(document());
  mocks.getContent.mockResolvedValue(content({ content: "# Not a heading\n\n- not a list" }));
  mount();
  expect(await screen.findByText(/# Not a heading/)).toBeVisible();
  expect(screen.queryByRole("heading", { name: "Not a heading" })).toBeNull();
  expect(screen.queryByRole("listitem")).toBeNull();
});

it("links straight to the readable report and mission the document came from", async () => {
  const links = [
    { kind: "report" as const, id: "report-1", title: "Synthesis report", href: "/reports/report-1" },
    { kind: "mission" as const, id: "mission-1", title: "Research run", href: "/missions/mission-1" },
  ];
  mocks.getDocument.mockResolvedValue(document({ source_report_id: "report-1", source_mission_id: "mission-1", source_origin: "synthesized", links }));
  mount();
  expect(await screen.findByRole("link", { name: "Open report" })).toHaveAttribute("href", "/reports/report-1");
  expect(screen.getByRole("link", { name: "Open mission" })).toHaveAttribute("href", "/missions/mission-1");
});

it("shows no report or mission link when none is readable", async () => {
  mount();
  expect(await screen.findByRole("heading", { name: "interview.txt" })).toBeVisible();
  expect(screen.queryByRole("link", { name: "Open report" })).toBeNull();
  expect(screen.queryByRole("link", { name: "Open mission" })).toBeNull();
  expect(screen.getByRole("link", { name: "Open project" })).toHaveAttribute("href", "/projects/project-1");
});

it("moves stats and metadata to Overview and loads chunks only on the Chunks tab", async () => {
  mount();
  expect(await screen.findByText("Full interview transcript body.")).toBeVisible();
  fireEvent.click(screen.getByRole("tab", { name: "Overview" }));
  expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Processing Status")).toBeVisible();
  expect(screen.getByText("Words")).toBeVisible();
  expect(screen.getByText("1,200")).toBeVisible();
  expect(screen.getByText("No processing history has been recorded.")).toBeVisible();
  expect(screen.queryByText("Full interview transcript body.")).toBeNull();
  fireEvent.click(screen.getByRole("tab", { name: "Chunks" }));
  await waitFor(() => expect(mocks.listChunks).toHaveBeenCalledWith("doc-1", { page: 1, pageSize: 10 }));
  expect(await screen.findByText("Document Chunks")).toBeVisible();
  fireEvent.keyDown(screen.getByRole("tab", { name: "Chunks" }), { key: "ArrowRight" });
  expect(screen.getByRole("tab", { name: "Evidence" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Linked evidence entries")).toBeVisible();
});

it("honours ?tab= deep links without fetching the text", async () => {
  mocks.query = { id: "doc-1", tab: "Overview" };
  mount();
  expect(await screen.findByText("Processing Status")).toBeVisible();
  expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  expect(mocks.getContent).not.toHaveBeenCalled();
});

it("falls back to Text for unknown ?tab= values", async () => {
  mocks.query = { id: "doc-1", tab: "bogus" };
  mount();
  expect(await screen.findByText("Full interview transcript body.")).toBeVisible();
  expect(screen.getByRole("tab", { name: "Text" })).toHaveAttribute("aria-selected", "true");
});

it("explains empty text and offers a retry when the text fails to load", async () => {
  mocks.getDocument.mockResolvedValue(document({ processed: false }));
  mocks.getContent.mockResolvedValue(content({ content: null }));
  const view = mount();
  expect(await screen.findByText("No text has been extracted from this document yet.")).toBeVisible();
  expect(screen.getByText(/Process the document to extract its text/)).toBeVisible();
  view.unmount();

  mocks.getContent.mockRejectedValueOnce(new Error("boom")).mockResolvedValue(content());
  mount();
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Document text could not be loaded.");
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("Full interview transcript body.")).toBeVisible();
});

describe("isMarkdownDocument", () => {
  it("keys off mime type, file name or synthesis origin, never the file_type category", () => {
    expect(isMarkdownDocument({ mime_type: "text/markdown", name: "a.txt" })).toBe(true);
    expect(isMarkdownDocument({ mime_type: "text/markdown; charset=utf-8", name: "a.txt" })).toBe(true);
    expect(isMarkdownDocument({ mime_type: "text/plain", name: "notes.MD" })).toBe(true);
    expect(isMarkdownDocument({ mime_type: "text/plain", name: "notes.markdown" })).toBe(true);
    expect(isMarkdownDocument({ mime_type: null, name: "report.txt", source_origin: "synthesized" })).toBe(true);
    expect(isMarkdownDocument({ mime_type: "text/plain", name: "report.txt", source_origin: "upload" })).toBe(false);
    expect(isMarkdownDocument({ mime_type: "application/pdf", name: "report.pdf" })).toBe(false);
  });
});
