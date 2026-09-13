import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { ExecutionTimeline } from "@/components/missions/ExecutionTimeline";
it("does not call a cancelled run a successful completion", () => {
  render(<ExecutionTimeline status="cancelled" createdAt="2026-09-13T00:00:00Z" queuedAt={null} startedAt={null} completedAt="2026-09-13T01:00:00Z" reportMetadata={null} />);
  expect(screen.queryByText("Execution Completed")).toBeNull();
  expect(screen.getByText("Run ended (cancelled)")).toBeVisible();
});
