import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { SWRConfig } from "swr";
import type { InboxItem, InboxPage as InboxPageData, InboxSummary } from "@/lib/api/inbox";

const mocks = vi.hoisted(() => ({ summary: vi.fn(), list: vi.fn(), markSeen: vi.fn(), review: vi.fn(), router: { isReady: true, query: {} as Record<string, string>, pathname: "/inbox", push: vi.fn() } }));
vi.mock("next/router", () => ({ useRouter: () => mocks.router }));
vi.mock("next/head", () => ({ default: () => null }));
vi.mock("@/lib/api/inbox", async original => ({ ...await original<object>(), inboxApi: { summary: mocks.summary, list: mocks.list, markSeen: mocks.markSeen } }));
vi.mock("@/lib/api/home", () => ({ homeApi: { review: mocks.review } }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { user_id: "reader" } }) }));
vi.mock("@/contexts/RoleContext", () => ({ useRole: () => ({ isAdmin: false }) }));
vi.mock("@/components/AuthGate", () => ({ AuthGate: ({ children }: { children: ReactNode }) => children }));

import InboxPage from "@/pages/inbox";
import { InboxAnnouncer } from "@/components/InboxBadge";
import { Navigation } from "@/components/Navigation";
import { parseApiTimestamp } from "@/lib/api/timestamps";
import { INBOX_SWR_OPTIONS } from "@/lib/hooks/useInboxSummary";

const generated = "2026-09-14T00:00:00.123456";
function summary(unread = { failures: 1, completions: 1, evidence: 1, total: 3 }): InboxSummary {
  return { generated_at: generated, refresh_seconds: 30, seen_through: "2026-09-13T00:00:00", default_lookback_seconds: 604800, unread };
}
const base = { status: null, updated_at: null, reviewed: null, entry_count: null, project_id: null, mission_id: null, session_key: null, origin: null };
const failure: InboxItem = { ...base, section: "failures", id: "m-fail", title: "Validate sources", label: "RESEARCH-9", status: "validation_failed", occurred_at: "2026-09-13T22:00:00", updated_at: "2026-09-13T22:00:00", unread: true, href: "/missions/m-fail" };
const completion: InboxItem = { ...failure, section: "completions", id: "m-done", title: "Summarize evidence", label: "RESEARCH-10", status: "completed", href: "/missions/m-done", reviewed: false, updated_at: "2026-09-13T21:30:00" };
const reviewed: InboxItem = { ...completion, id: "m-seen", title: "Already reviewed", reviewed: true, unread: false };
const evidence: InboxItem = { ...base, section: "evidence", id: "p:m-done:worker-run:deepsearch-worker", title: "worker-run", label: "deepsearch-worker", occurred_at: "2026-09-13T23:00:00", unread: true, href: "/evidence?project_id=p&mission_id=m-done&session_key=worker-run", entry_count: 12, project_id: "p", mission_id: "m-done", session_key: "worker-run", origin: "deepsearch-worker" };
const pages: Record<string, InboxItem[]> = { failures: [failure], completions: [completion, reviewed], evidence: [evidence] };
function page(section: string, items = pages[section]): InboxPageData {
  return { section: section as InboxPageData["section"], generated_at: generated, seen_through: "2026-09-13T00:00:00", total: items.length, items };
}
function mount(ui: ReactNode = <InboxPage />) {
  return render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}>{ui}</SWRConfig>);
}
beforeEach(() => {
  vi.resetAllMocks();
  mocks.router.query = {};
  mocks.router.isReady = true;
  mocks.summary.mockResolvedValue(summary());
  mocks.list.mockImplementation(async (section: string) => page(section));
});

describe("the priority inbox", () => {
  it("renders failures, completions and evidence in priority order with server totals, unread marks and canonical links", async () => {
    mount();
    const headings = await screen.findAllByRole("heading", { level: 2 });
    expect(headings.map(heading => heading.textContent)).toEqual([expect.stringContaining("Agent failures"), expect.stringContaining("Mission completions"), expect.stringContaining("New evidence")]);
    expect(screen.getByRole("link", { name: "Validate sources" })).toHaveAttribute("href", "/missions/m-fail");
    expect(screen.getByRole("link", { name: "12 evidence entries" })).toHaveAttribute("href", "/evidence?project_id=p&mission_id=m-done&session_key=worker-run");
    expect(screen.getAllByText("Unread")).toHaveLength(3);
    expect(screen.getByText("3 unread")).toBeVisible();
    expect(screen.getByText("Reviewed")).toBeVisible();
    expect(mocks.list).toHaveBeenCalledWith("failures", { page: 1 });
    const expected = parseApiTimestamp(failure.occurred_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
    const stamp = [...document.querySelectorAll("time")].find(node => node.getAttribute("datetime") === failure.occurred_at);
    expect(stamp).toHaveTextContent(expected);
  });

  it("marks all as seen with the server's generated_at string verbatim and refreshes every count", async () => {
    mount();
    const button = await screen.findByRole("button", { name: "Mark all as seen" });
    await screen.findByText("3 unread");
    mocks.markSeen.mockResolvedValue({ seen_through: generated });
    mocks.summary.mockResolvedValue(summary({ failures: 0, completions: 0, evidence: 0, total: 0 }));
    mocks.list.mockImplementation(async (section: string) => page(section, pages[section].map(item => ({ ...item, unread: false }))));
    fireEvent.click(button);
    await waitFor(() => expect(mocks.markSeen).toHaveBeenCalledWith(generated));
    expect(await screen.findByText("0 unread")).toBeVisible();
    await waitFor(() => expect(screen.queryAllByText("Unread")).toHaveLength(0));
    expect(screen.getByRole("button", { name: "Mark all as seen" })).toBeDisabled();
  });

  it("reviews a completion through Home's review route and keeps a failed review visible", async () => {
    mount();
    mocks.review.mockRejectedValueOnce(new Error("changed"));
    fireEvent.click(await screen.findByRole("button", { name: "Mark reviewed" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Review could not be saved");
    expect(screen.getByRole("link", { name: "Summarize evidence" })).toBeVisible();
    mocks.review.mockResolvedValueOnce(undefined);
    mocks.list.mockImplementation(async (section: string) => page(section, section === "completions" ? [{ ...completion, reviewed: true, unread: false }, reviewed] : pages[section]));
    fireEvent.click(screen.getByRole("button", { name: "Mark reviewed" }));
    await waitFor(() => expect(mocks.review).toHaveBeenLastCalledWith({ id: "m-done", updated_at: "2026-09-13T21:30:00" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Mark reviewed" })).toBeNull());
    expect(screen.getAllByText("Reviewed")).toHaveLength(2);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("keeps loading, empty and error states distinct per section and retries in place", async () => {
    let release!: (value: InboxPageData) => void;
    mocks.list.mockImplementation((section: string) => section === "failures" ? new Promise<InboxPageData>(resolve => { release = resolve; }) : section === "completions" ? Promise.reject(new Error("offline")) : Promise.resolve(page(section, [])));
    mount();
    expect(await screen.findByText("Loading agent failures…")).toBeVisible();
    expect(await screen.findByText("Mission completions could not load.")).toBeVisible();
    expect(await screen.findByText("No new evidence.")).toBeVisible();
    await act(async () => release(page("failures", [])));
    expect(await screen.findByText("No agent failures.")).toBeVisible();
    expect(screen.queryByText("Loading agent failures…")).toBeNull();
    mocks.list.mockImplementation(async (section: string) => page(section, []));
    fireEvent.click(within(screen.getByText("Mission completions could not load.").closest("[role=alert]") as HTMLElement).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No completed missions.")).toBeVisible();
  });

  it("shows a not-found state for an unknown section and focuses a known one", async () => {
    mocks.router.query = { section: "bogus" };
    const view = mount();
    expect(await screen.findByText("Inbox section not found")).toBeVisible();
    expect(screen.getByRole("link", { name: "Open the full inbox" })).toHaveAttribute("href", "/inbox");
    expect(mocks.list).not.toHaveBeenCalled();
    view.unmount();
    mocks.router.query = { section: "completions" };
    mount();
    expect((await screen.findAllByRole("heading", { level: 2 })).map(heading => heading.textContent)).toEqual([expect.stringContaining("Mission completions")]);
    expect(screen.getByRole("link", { name: /Mission completions/ })).toHaveAttribute("aria-current", "page");
    expect(mocks.list).toHaveBeenCalledTimes(1);
  });
});

describe("the shell badge", () => {
  it.each([[3, "3"], [120, "99+"]])("names the Inbox navigation item by its unread count (%i)", async (total, badge) => {
    mocks.summary.mockResolvedValue(summary({ failures: total, completions: 0, evidence: 0, total }));
    mount(<Navigation />);
    const link = await screen.findByRole("link", { name: `Inbox, ${total} unread` });
    expect(link).toHaveAttribute("href", "/inbox");
    expect(within(link).getByTestId("inbox-unread")).toHaveTextContent(badge);
  });

  it("hides the badge at zero and keeps the plain Inbox name", async () => {
    mocks.summary.mockResolvedValue(summary({ failures: 0, completions: 0, evidence: 0, total: 0 }));
    mount(<Navigation />);
    await waitFor(() => expect(mocks.summary).toHaveBeenCalled());
    expect(screen.getByRole("link", { name: "Inbox", exact: true })).toBeVisible();
    expect(screen.queryByTestId("inbox-unread")).toBeNull();
    expect(screen.queryByRole("link", { name: /unread/ })).toBeNull();
  });

  it("announces unread increases politely and stays silent on first load and decreases", () => {
    const view = render(<InboxAnnouncer total={undefined} />);
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    view.rerender(<InboxAnnouncer total={1} />);
    expect(status.textContent).toBe("");
    view.rerender(<InboxAnnouncer total={3} />);
    expect(status.textContent).toBe("3 unread inbox items");
    view.rerender(<InboxAnnouncer total={2} />);
    expect(status.textContent).toBe("");
    view.rerender(<InboxAnnouncer total={3} />);
    expect(status.textContent).toBe("3 unread inbox items");
  });

  it("polls at the server's refresh interval, pauses hidden tabs and revalidates on focus", () => {
    expect(INBOX_SWR_OPTIONS.refreshInterval({ ...summary(), refresh_seconds: 45 })).toBe(45000);
    expect(INBOX_SWR_OPTIONS.refreshInterval(undefined)).toBe(30000);
    expect(INBOX_SWR_OPTIONS.refreshWhenHidden).toBe(false);
    expect(INBOX_SWR_OPTIONS.revalidateOnFocus).toBe(true);
  });
});
