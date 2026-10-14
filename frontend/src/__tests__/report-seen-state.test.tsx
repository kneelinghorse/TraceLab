import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { SWRConfig } from "swr";
const mocks = vi.hoisted(() => ({ list: vi.fn(), markViewed: vi.fn() }));
vi.mock("next/router", () => ({ useRouter: () => ({ query: {} }) }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { user_id: "reader" } }) }));
vi.mock("@/components/AuthGate", () => ({ AuthGate: ({ children }: { children: ReactNode }) => children }));
vi.mock("@/lib/api/projects", () => ({ projectsApi: { listAllProjects: async () => [] } }));
vi.mock("@/lib/api/reports", () => ({ reportsApi: { list: mocks.list } }));
vi.mock("@/lib/hooks/useActivitySummary", () => ({ markViewed: mocks.markViewed, useActivityState: () => ({ data: { items: [{ type: "report", id: "copy", viewed: false, new: true }] }, mutate: vi.fn() }) }));
import ReportsPage from "@/pages/reports";
const stamp = "2026-10-14T00:00:00Z";
beforeEach(() => {
  mocks.markViewed.mockReset();
  mocks.list.mockResolvedValue({ items: [{ id: "copy", title: "Mission copy", origin: "mission", origin_label: "Results of mission Research", origin_href: "/missions/run?tab=results", status: "draft", created_at: stamp, updated_at: stamp }], total: 1, page: 1, page_size: 20 });
});
it("opening a mission-result title acknowledges the report copy even though its destination is the mission", async () => {
  render(<SWRConfig value={{ provider: () => new Map() }}><ReportsPage /></SWRConfig>);
  const title = await screen.findByRole("link", { name: "Mission copy", exact: true });
  expect(title).toHaveAttribute("href", "/missions/run?tab=results");
  expect(mocks.markViewed).not.toHaveBeenCalled();
  fireEvent.click(title);
  await waitFor(() => expect(mocks.markViewed).toHaveBeenCalledWith([{ type: "report", id: "copy", occurred_at: stamp }]));
});
it("counts a single result in the singular, which the Sprint 67 walkthrough showed as '1 mission results'", async () => {
  const { unmount } = render(<SWRConfig value={{ provider: () => new Map() }}><ReportsPage /></SWRConfig>);
  fireEvent.click(await screen.findByRole("button", { name: "Mission results", exact: true }));
  expect(await screen.findByText("1 mission result")).toBeInTheDocument();
  unmount();
  mocks.list.mockResolvedValue({ items: [], total: 2, page: 1, page_size: 20 });
  render(<SWRConfig value={{ provider: () => new Map() }}><ReportsPage /></SWRConfig>);
  expect(await screen.findByText("2 reports")).toBeInTheDocument();
});
