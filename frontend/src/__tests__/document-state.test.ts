import { describe, expect, it } from "vitest";
import { documentState } from "@/lib/document-state";

describe("truthful document status projection", () => {
  it.each([
    [{}, "Unknown"],
    [{ processed: false, chunked: false, embedded: false }, "Pending"],
    [{ processed: true }, "Processed"],
    [{ chunked: true }, "Chunked"],
    [{ embedded: true }, "Embedded"],
  ])("keeps missing stages distinct from pending", (input, label) => expect(documentState(input).label).toBe(label));
  it("shows a new processing failure despite old completed booleans, but lets a later success supersede it", () => {
    const failure = { id: "failure", document_id: "doc", stage: "parsing", status: "failed", created_at: "2026-09-13T10:00:00", updated_at: "2026-09-13T10:00:00" };
    expect(documentState({ embedded: true, processing_events: [failure] }).label).toBe("Failed");
    const success = { ...failure, id: "success", status: "succeeded", created_at: "2026-09-13T11:00:00" };
    expect(documentState({ embedded: true, processing_events: [failure, success] }).label).toBe("Embedded");
  });
});
