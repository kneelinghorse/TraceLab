import { beforeEach, describe, expect, it, vi } from "vitest";

const http = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock("@/lib/api/http", () => ({ httpClient: http }));

import { ANSWER_BUDGETS, librarianApi, replyToTranscriptText } from "@/lib/api/librarian";

beforeEach(() => {
  http.post.mockReset().mockResolvedValue({});
});

const messages = [{ role: "user" as const, content: "What does self-hosting Qdrant cost?" }];

// Pins what goes on the wire: the page tests mock this module, so a dropped
// budget would otherwise pass them and bring the truncation back (QA-1).
describe("librarianApi.turn HTTP contract", () => {
  it("a conversational turn sends the transcript and project only", async () => {
    await librarianApi.turn(messages, "project-1");
    expect(http.post).toHaveBeenCalledWith("/librarian/turns", { project_id: "project-1", messages });
  });

  it("an answer turn carries answer mode and the chosen budget", async () => {
    await librarianApi.turn(messages, "project-1", { maxTokens: ANSWER_BUDGETS.full });
    expect(http.post).toHaveBeenCalledWith("/librarian/turns", {
      project_id: "project-1",
      messages,
      mode: "answer",
      max_tokens: 2000,
    });
  });
});

describe("replyToTranscriptText", () => {
  it("names a cited chunk by document and number, and evidence by id", () => {
    const chunk = {
      id: "chunk-9",
      document_id: "doc-1",
      document_name: "qdrant-on-railway.md",
      chunk_index: 9,
      snippet: null,
      href: "/documents/doc-1?chunk=chunk-9&index=9",
    };
    const text = replyToTranscriptText(
      [
        { kind: "corpus_claim", text: "The bill is $48.", citations: ["chunk-9"] },
        { kind: "corpus_claim", text: "Interviews mention cost.", citations: ["entry-1"] },
      ],
      [chunk],
    );
    expect(text).toBe(
      "The bill is $48. [document qdrant-on-railway.md, chunk 9]\n\nInterviews mention cost. [evidence:entry-1]",
    );
  });
});
