import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  role: { role: "admin" as string | null, status: "ready" as string, isAdmin: true },
  auth: { user: { user_id: "self", email: "me@x.com", display_name: "Me" } },
  spaces: {
    list: vi.fn(),
    create: vi.fn(),
    listMembers: vi.fn(),
    addMember: vi.fn(),
    removeMember: vi.fn(),
    assignProjectSpace: vi.fn(),
  },
  users: { list: vi.fn() },
  projects: { listProjects: vi.fn() },
}));

vi.mock("@/contexts/RoleContext", () => ({ useRole: () => mocks.role }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => mocks.auth }));
vi.mock("@/lib/api/admin", () => ({ adminSpacesApi: mocks.spaces, adminUsersApi: mocks.users }));
vi.mock("@/lib/api/projects", () => ({ projectsApi: mocks.projects }));

import { SpacesAdmin } from "@/pages/admin/spaces";

const SPACES = [
  { id: "s1", name: "Research", created_at: "2026-01-01T00:00:00Z" },
  { id: "s2", name: "Ops", created_at: "2026-01-02T00:00:00Z" },
];

const USERS = [
  { id: "u1", email: "alice@x.com", display_name: "Alice", role: "member", is_active: true, created_at: "", last_login_at: null },
  { id: "u2", email: "bob@x.com", display_name: "Bob", role: "member", is_active: true, created_at: "", last_login_at: null },
  { id: "u3", email: "carol@x.com", display_name: "Carol", role: "viewer", is_active: false, created_at: "", last_login_at: null },
];

const PROJECTS = [
  { id: "p1", name: "Proj 1", workspace_id: null },
  { id: "p2", name: "Proj 2", workspace_id: "s1" },
];

const MEMBERS_S1 = [
  { user_id: "u1", email: "alice@x.com", display_name: "Alice", role: "member", is_active: true, created_at: "" },
];

function optionValues(select: HTMLElement): string[] {
  return within(select)
    .getAllByRole("option")
    .map((o) => (o as HTMLOptionElement).value);
}

beforeEach(() => {
  mocks.role = { role: "admin", status: "ready", isAdmin: true };
  mocks.spaces.list.mockReset().mockResolvedValue(SPACES);
  mocks.spaces.create.mockReset().mockResolvedValue({ id: "s3", name: "New Space", created_at: "" });
  mocks.spaces.listMembers.mockReset().mockResolvedValue(MEMBERS_S1);
  mocks.spaces.addMember.mockReset().mockResolvedValue({});
  mocks.spaces.removeMember.mockReset().mockResolvedValue({});
  mocks.spaces.assignProjectSpace.mockReset().mockResolvedValue({});
  mocks.users.list.mockReset().mockResolvedValue(USERS);
  mocks.projects.listProjects.mockReset().mockResolvedValue({
    data: PROJECTS,
    pagination: { page: 1, page_size: 100, total: 2, pages: 1 },
  });
});

// Space names also appear as <option>s in the project-assignment selects, so
// scope list-row lookups to the <span> that renders the name in the spaces list.
async function renderLoaded() {
  render(<SpacesAdmin />);
  await waitFor(() => expect(screen.getByText("Research", { selector: "span" })).toBeTruthy());
}

async function manageMembers(spaceName: string) {
  const row = screen.getByText(spaceName, { selector: "span" }).closest("li") as HTMLElement;
  fireEvent.click(within(row).getByRole("button", { name: "Manage members" }));
  // The per-member "Remove" button only renders once the roster has loaded.
  await waitFor(() => expect(screen.getByRole("button", { name: "Remove" })).toBeTruthy());
}

describe("SpacesAdmin", () => {
  it("lists spaces", async () => {
    await renderLoaded();
    expect(screen.getByText("Ops", { selector: "span" })).toBeTruthy();
  });

  it("creates a space and reloads the list", async () => {
    await renderLoaded();
    fireEvent.change(screen.getByLabelText("Space name"), { target: { value: "New Space" } });
    fireEvent.click(screen.getByRole("button", { name: /create space/i }));
    await waitFor(() => expect(mocks.spaces.create).toHaveBeenCalledWith("New Space"));
    await waitFor(() => expect(mocks.spaces.list).toHaveBeenCalledTimes(2));
  });

  it("blocks a blank space name client-side", async () => {
    await renderLoaded();
    fireEvent.change(screen.getByLabelText("Space name"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: /create space/i }));
    expect(await screen.findByText(/cannot be blank/i)).toBeTruthy();
    expect(mocks.spaces.create).not.toHaveBeenCalled();
  });

  it("loads a space's members and offers only active non-members in the picker", async () => {
    await renderLoaded();
    await manageMembers("Research");
    expect(mocks.spaces.listMembers).toHaveBeenCalledWith("s1");
    // Picker excludes Alice (already a member) and Carol (inactive) → only Bob.
    expect(optionValues(screen.getByLabelText("Add member to space"))).toEqual(["", "u2"]);
  });

  it("adds a member", async () => {
    await renderLoaded();
    await manageMembers("Research");
    fireEvent.change(screen.getByLabelText("Add member to space"), { target: { value: "u2" } });
    fireEvent.click(screen.getByRole("button", { name: "Add member" }));
    await waitFor(() => expect(mocks.spaces.addMember).toHaveBeenCalledWith("s1", "u2"));
  });

  it("removes a member", async () => {
    await renderLoaded();
    await manageMembers("Research");
    // Alice (u1) is the only member, so the single Remove button is hers.
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(mocks.spaces.removeMember).toHaveBeenCalledWith("s1", "u1"));
  });

  it("assigns a project to a space and un-assigns it", async () => {
    await renderLoaded();
    fireEvent.change(screen.getByLabelText("Space for Proj 1"), { target: { value: "s1" } });
    await waitFor(() => expect(mocks.spaces.assignProjectSpace).toHaveBeenCalledWith("p1", "s1"));

    // Proj 2 starts in s1; selecting "— No Space —" un-assigns (null).
    fireEvent.change(screen.getByLabelText("Space for Proj 2"), { target: { value: "" } });
    await waitFor(() => expect(mocks.spaces.assignProjectSpace).toHaveBeenCalledWith("p2", null));
  });

  it("surfaces a 409 when adding a duplicate member", async () => {
    mocks.spaces.addMember.mockRejectedValueOnce(
      new Error('{"detail":"User is already a member of this Space"}'),
    );
    await renderLoaded();
    await manageMembers("Research");
    fireEvent.change(screen.getByLabelText("Add member to space"), { target: { value: "u2" } });
    fireEvent.click(screen.getByRole("button", { name: "Add member" }));
    expect(await screen.findByText("User is already a member of this Space")).toBeTruthy();
  });

  it("does not PATCH when a project's Space selection is unchanged", async () => {
    await renderLoaded();
    // Proj 2 is already in s1; re-selecting s1 must be a no-op.
    fireEvent.change(screen.getByLabelText("Space for Proj 2"), { target: { value: "s1" } });
    expect(mocks.spaces.assignProjectSpace).not.toHaveBeenCalled();
  });

  it("disables Add member until a user is picked", async () => {
    await renderLoaded();
    await manageMembers("Research");
    const addBtn = screen.getByRole("button", { name: "Add member" }) as HTMLButtonElement;
    expect(addBtn.disabled).toBe(true);
  });

  it("resets the member picker when switching spaces", async () => {
    await renderLoaded();
    await manageMembers("Research");
    fireEvent.change(screen.getByLabelText("Add member to space"), { target: { value: "u2" } });
    expect((screen.getByLabelText("Add member to space") as HTMLSelectElement).value).toBe("u2");

    const opsRow = screen.getByText("Ops", { selector: "span" }).closest("li") as HTMLElement;
    fireEvent.click(within(opsRow).getByRole("button", { name: "Manage members" }));
    await waitFor(() => expect(mocks.spaces.listMembers).toHaveBeenCalledWith("s2"));
    await waitFor(() =>
      expect((screen.getByLabelText("Add member to space") as HTMLSelectElement).value).toBe(""),
    );
  });

  it("ignores a stale roster response when the space is switched mid-fetch", async () => {
    let resolveS1!: (v: unknown) => void;
    let resolveS2!: (v: unknown) => void;
    mocks.spaces.listMembers.mockImplementation((id: string) =>
      id === "s1"
        ? new Promise((r) => {
            resolveS1 = r;
          })
        : new Promise((r) => {
            resolveS2 = r;
          }),
    );
    await renderLoaded();

    // Select Research (s1), then Ops (s2) before either roster resolves.
    fireEvent.click(
      within(screen.getByText("Research", { selector: "span" }).closest("li") as HTMLElement).getByRole(
        "button",
        { name: "Manage members" },
      ),
    );
    fireEvent.click(
      within(screen.getByText("Ops", { selector: "span" }).closest("li") as HTMLElement).getByRole(
        "button",
        { name: "Manage members" },
      ),
    );

    // The current selection (s2) resolves to Bob.
    resolveS2([
      { user_id: "u2", email: "bob@x.com", display_name: "Bob", role: "member", is_active: true, created_at: "" },
    ]);
    expect(await screen.findByText(/Bob/)).toBeTruthy();

    // The superseded s1 fetch resolves LATER — it must be ignored, not shown.
    // (Alice legitimately appears in the s2 picker as an eligible non-member, so
    // scope the check to the roster row behind the single Remove button.)
    resolveS1([
      { user_id: "u1", email: "alice@x.com", display_name: "Alice", role: "member", is_active: true, created_at: "" },
    ]);
    await waitFor(() => {
      const rosterRow = screen.getByRole("button", { name: "Remove" }).closest("li") as HTMLElement;
      expect(within(rosterRow).getByText(/Bob/)).toBeTruthy();
      expect(within(rosterRow).queryByText(/Alice/)).toBeNull();
    });
  });

  it("surfaces an assignment failure", async () => {
    mocks.spaces.assignProjectSpace.mockRejectedValueOnce(new Error('{"detail":"Space not found"}'));
    await renderLoaded();
    fireEvent.change(screen.getByLabelText("Space for Proj 1"), { target: { value: "s2" } });
    expect(await screen.findByText("Space not found")).toBeTruthy();
  });

  it("surfaces a spaces load failure", async () => {
    mocks.spaces.list.mockReset().mockRejectedValue(new Error('{"detail":"Failed to read spaces"}'));
    render(<SpacesAdmin />);
    expect(await screen.findByText("Failed to read spaces")).toBeTruthy();
  });
});
