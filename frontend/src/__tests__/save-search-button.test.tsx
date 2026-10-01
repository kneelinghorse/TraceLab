import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SaveSearchButton } from "@/components/SaveSearchButton";
import { savedSearchesApi } from "@/lib/api/savedSearches";

vi.mock("@/lib/api/savedSearches", () => ({ savedSearchesApi: { create: vi.fn() } }));
const create = vi.mocked(savedSearchesApi.create);
const filters = { projectId: "project-a", documentType: "transcript", startDate: "2026-09-01", endDate: "2026-09-30" };
const props = { currentQuery: "reviewed query", filters, topK: 7, savedSearchCount: 0, limitPerUser: 50 };
const open = () => fireEvent.click(screen.getByRole("button", { name: "Save current search", exact: true }));
const save = () => fireEvent.click(screen.getByRole("button", { name: "Save search", exact: true }));

beforeEach(() => vi.resetAllMocks());

describe("manual saved-search draft", () => {
  it("saves the scope the reader reviewed even when parent props change during an error and retry", async () => {
    create.mockRejectedValueOnce(new Error("Please retry"));
    const onSaved = vi.fn();
    const { rerender } = render(<SaveSearchButton {...props} onSaved={onSaved} />);
    open();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "  Weekly review  " } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "  Reviewed scope  " } });
    rerender(<SaveSearchButton {...props} currentQuery="new query" filters={{ ...filters, projectId: "project-b" }} topK={20} onSaved={onSaved} />);
    expect(screen.getByText("reviewed query")).toBeVisible();
    expect(screen.getByText("Top K: 7")).toBeVisible();
    save();
    expect(await screen.findByText("Please retry")).toBeVisible();
    expect(onSaved).not.toHaveBeenCalled();
    const payload = { name: "Weekly review", description: "Reviewed scope", query_text: "reviewed query", search_mode: "semantic", top_k: 7, filters: { project_id: "project-a", source_type: "transcript", date_from: "2026-09-01", date_to: "2026-09-30" } };
    expect(create).toHaveBeenNthCalledWith(1, payload);
    create.mockResolvedValueOnce({ id: "saved" } as Awaited<ReturnType<typeof savedSearchesApi.create>>);
    save();
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(create).toHaveBeenNthCalledWith(2, payload);
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
  });

  it("cancel discards edits and reopening captures the new query, scope and limit", async () => {
    const { rerender } = render(<SaveSearchButton {...props} />);
    open();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Discard this" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Discard this too" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(create).not.toHaveBeenCalled();
    rerender(<SaveSearchButton {...props} currentQuery="fresh query" filters={{ projectId: "", documentType: "", startDate: "", endDate: "" }} topK={20} />);
    open();
    expect(screen.getByLabelText("Name")).toHaveValue("fresh query");
    expect(screen.getByLabelText("Description")).toHaveValue("");
    expect(screen.getByText("Top K: 20")).toBeVisible();
    save();
    await waitFor(() => expect(create).toHaveBeenCalledWith({ name: "fresh query", description: undefined, query_text: "fresh query", search_mode: "semantic", top_k: 20, filters: {} }));
  });

  it("does not create an unnamed, blank-query or over-limit saved search", () => {
    const { rerender } = render(<SaveSearchButton {...props} currentQuery="  " />);
    open();
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
    rerender(<SaveSearchButton {...props} savedSearchCount={50} />);
    expect(screen.getByRole("button", { name: "Save current search" })).toBeDisabled();
    rerender(<SaveSearchButton {...props} />);
    open();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "  " } });
    save();
    expect(screen.getByText("Name is required.")).toBeVisible();
    expect(create).not.toHaveBeenCalled();
  });
});
