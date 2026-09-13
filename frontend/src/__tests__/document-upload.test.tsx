import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ uploadDocument: vi.fn(), processDocument: vi.fn() }));
vi.mock("@/lib/api/documents", () => ({ documentsApi: mocks }));
import { DocumentUpload } from "@/components/documents/DocumentUpload";

beforeEach(() => { vi.clearAllMocks(); });
function select(...names: string[]) {
  fireEvent.change(screen.getByLabelText("Choose files"), { target: { files: names.map(name => new File(["Research source"], name, { type: "text/plain" })) } });
}

describe("independent document uploads", () => {
  it("keeps a rejected file visible and still uploads the next file", async () => {
    mocks.uploadDocument.mockRejectedValueOnce(new Error("Unsupported file type")).mockResolvedValueOnce({ id: "good-doc" });
    mocks.processDocument.mockResolvedValue({ status: "completed" });
    render(<DocumentUpload projectId="project" />);
    select("rejected.bin", "source.txt");
    fireEvent.click(screen.getByRole("button", { name: "Upload files" }));
    expect(await screen.findByText("Unsupported file type")).toBeVisible();
    expect(await screen.findByRole("link", { name: "Open source.txt" })).toHaveAttribute("href", "/documents/good-doc");
    expect(mocks.uploadDocument).toHaveBeenCalledTimes(2);
    expect(mocks.processDocument).toHaveBeenCalledWith("good-doc");
  });

  it("shows observed byte progress without claiming the server accepted the file", async () => {
    let report: (loaded: number, total: number | null) => void = () => {};
    let finish: (value: { id: string }) => void = () => {};
    mocks.uploadDocument.mockImplementation((_project, _file, progress) => { report = progress; return new Promise(resolve => { finish = resolve; }); });
    render(<DocumentUpload projectId="project" />);
    select("source.txt");
    fireEvent.click(screen.getByLabelText("Process after upload"));
    fireEvent.click(screen.getByRole("button", { name: "Upload files" }));
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
    act(() => report(50, 100));
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
    act(() => report(100, 100));
    expect(screen.queryByRole("link", { name: "Open source.txt" })).toBeNull();
    await act(async () => finish({ id: "saved" }));
    expect(await screen.findByText("Uploaded")).toBeVisible();
  });

  it("retries failed processing on the saved document instead of uploading a duplicate", async () => {
    mocks.uploadDocument.mockResolvedValue({ id: "saved" });
    mocks.processDocument.mockRejectedValueOnce(new Error("Parser unavailable")).mockResolvedValueOnce({ status: "completed" });
    render(<DocumentUpload projectId="project" />);
    select("source.txt");
    fireEvent.click(screen.getByRole("button", { name: "Upload files" }));
    expect(await screen.findByText("Parser unavailable")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry source.txt" }));
    await waitFor(() => expect(mocks.processDocument).toHaveBeenCalledTimes(2));
    expect(mocks.uploadDocument).toHaveBeenCalledOnce();
    expect(await screen.findByText("Processing completed")).toBeVisible();
  });

  it("preserves a failed pipeline stage even when the outer response says completed", async () => {
    mocks.uploadDocument.mockResolvedValue({ id: "saved" });
    mocks.processDocument.mockResolvedValue({ status: "completed", stages: { embedding: { status: "failed" } } });
    render(<DocumentUpload projectId="project" />);
    select("source.txt");
    fireEvent.click(screen.getByRole("button", { name: "Upload files" }));
    expect(await screen.findByText(/Processing needs attention: embedding/)).toBeVisible();
    expect(within(screen.getByRole("list", { name: "Upload results" })).queryByText("Processing completed")).toBeNull();
  });
});
