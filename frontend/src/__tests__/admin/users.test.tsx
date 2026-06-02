import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  role: { role: "admin" as string | null, status: "ready" as string, isAdmin: true },
  auth: {
    user: { user_id: "self-id", email: "me@x.com", display_name: "Me" } as
      | { user_id: string; email: string; display_name: string }
      | null,
  },
  api: {
    list: vi.fn(),
    create: vi.fn(),
    setRole: vi.fn(),
    setActive: vi.fn(),
    remove: vi.fn(),
  },
}));

vi.mock("@/contexts/RoleContext", () => ({ useRole: () => mocks.role }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => mocks.auth }));
vi.mock("@/lib/api/admin", () => ({ adminUsersApi: mocks.api }));

import { UsersAdmin } from "@/pages/admin/users";

function sampleUsers() {
  return [
    {
      id: "self-id",
      email: "me@x.com",
      display_name: "Me",
      role: "admin",
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
      last_login_at: null,
    },
    {
      id: "u2",
      email: "bob@x.com",
      display_name: "Bob",
      role: "member",
      is_active: true,
      created_at: "2026-01-02T00:00:00Z",
      last_login_at: null,
    },
    {
      id: "u3",
      email: "carol@x.com",
      display_name: "Carol",
      role: "viewer",
      is_active: false,
      created_at: "2026-01-03T00:00:00Z",
      last_login_at: null,
    },
    {
      id: "u4",
      email: "olivia@x.com",
      display_name: "Olivia",
      role: "owner",
      is_active: true,
      created_at: "2026-01-04T00:00:00Z",
      last_login_at: null,
    },
  ];
}

function optionValues(select: HTMLElement): string[] {
  return within(select)
    .getAllByRole("option")
    .map((o) => (o as HTMLOptionElement).value);
}

beforeEach(() => {
  mocks.role = { role: "admin", status: "ready", isAdmin: true };
  mocks.auth = { user: { user_id: "self-id", email: "me@x.com", display_name: "Me" } };
  mocks.api.list.mockReset().mockResolvedValue(sampleUsers());
  mocks.api.create.mockReset().mockResolvedValue({
    id: "new",
    email: "new@x.com",
    display_name: "New User",
    role: "member",
    is_active: true,
    created_at: "2026-02-01T00:00:00Z",
    last_login_at: null,
  });
  mocks.api.setRole.mockReset().mockResolvedValue({});
  mocks.api.setActive.mockReset().mockResolvedValue({});
  mocks.api.remove.mockReset().mockResolvedValue({ success: true, id: "u2", message: "deleted" });
});

async function renderLoaded() {
  render(<UsersAdmin />);
  await waitFor(() => expect(screen.getByText("bob@x.com")).toBeTruthy());
}

describe("UsersAdmin — list + lifecycle", () => {
  it("lists users from the API", async () => {
    await renderLoaded();
    expect(screen.getByText("carol@x.com")).toBeTruthy();
    expect(mocks.api.list).toHaveBeenCalledTimes(1);
  });

  it("creates a user at a role and reloads the list", async () => {
    await renderLoaded();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@x.com" } });
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "New User" } });
    fireEvent.change(screen.getByLabelText("Temporary password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /create user/i }));

    await waitFor(() =>
      expect(mocks.api.create).toHaveBeenCalledWith({
        email: "new@x.com",
        display_name: "New User",
        password: "password123",
        role: "member",
      }),
    );
    await waitFor(() => expect(mocks.api.list).toHaveBeenCalledTimes(2));
    // Success feedback shown and the form cleared.
    expect(await screen.findByText(/Created new@x.com as member/i)).toBeTruthy();
    expect((screen.getByLabelText("Email") as HTMLInputElement).value).toBe("");
  });

  it("enables a disabled user (toggle direction is not hardcoded)", async () => {
    await renderLoaded();
    const carolRow = screen.getByText("carol@x.com").closest("tr") as HTMLElement;
    fireEvent.click(within(carolRow).getByRole("button", { name: "Enable" }));
    await waitFor(() => expect(mocks.api.setActive).toHaveBeenCalledWith("u3", true));
  });

  it("does not PATCH the role when the selection is unchanged", async () => {
    await renderLoaded();
    fireEvent.change(screen.getByLabelText("Role for bob@x.com"), { target: { value: "member" } });
    expect(mocks.api.setRole).not.toHaveBeenCalled();
  });

  it("changes a user's role", async () => {
    await renderLoaded();
    fireEvent.change(screen.getByLabelText("Role for bob@x.com"), { target: { value: "admin" } });
    await waitFor(() => expect(mocks.api.setRole).toHaveBeenCalledWith("u2", "admin"));
  });

  it("disables a user", async () => {
    await renderLoaded();
    const bobRow = screen.getByText("bob@x.com").closest("tr") as HTMLElement;
    fireEvent.click(within(bobRow).getByRole("button", { name: "Disable" }));
    await waitFor(() => expect(mocks.api.setActive).toHaveBeenCalledWith("u2", false));
  });

  it("requires confirmation (with the cascade warning) before deleting", async () => {
    await renderLoaded();
    const bobRow = screen.getByText("bob@x.com").closest("tr") as HTMLElement;
    fireEvent.click(within(bobRow).getByRole("button", { name: "Delete" }));

    // No API call yet — a confirm dialog with the owner-clear cascade warning appears.
    expect(mocks.api.remove).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/owner is cleared/i)).toBeTruthy();

    fireEvent.click(within(dialog).getByRole("button", { name: "Delete user" }));
    await waitFor(() => expect(mocks.api.remove).toHaveBeenCalledWith("u2"));
  });

  it("disables the delete control for your own account", async () => {
    await renderLoaded();
    const selfRow = screen.getByText("me@x.com").closest("tr") as HTMLElement;
    const del = within(selfRow).getByRole("button", { name: "Delete" }) as HTMLButtonElement;
    expect(del.disabled).toBe(true);
  });
});

describe("UsersAdmin — owner-gating", () => {
  it("hides the owner role option from an admin caller", async () => {
    await renderLoaded();
    expect(optionValues(screen.getByLabelText("New user role"))).toEqual([
      "viewer",
      "member",
      "admin",
      "service",
    ]);
    // A member row's role select also omits owner for an admin caller...
    expect(optionValues(screen.getByLabelText("Role for bob@x.com"))).not.toContain("owner");
    // ...but an owner row still SHOWS owner as its current value (controlled <select>).
    expect(optionValues(screen.getByLabelText("Role for olivia@x.com"))).toContain("owner");
  });

  it("offers the owner role option to an owner caller", async () => {
    mocks.role = { role: "owner", status: "ready", isAdmin: true };
    await renderLoaded();
    expect(optionValues(screen.getByLabelText("New user role"))).toContain("owner");
  });
});

describe("UsersAdmin — error surfacing", () => {
  it("surfaces a 409 duplicate-email error from create", async () => {
    mocks.api.create.mockRejectedValueOnce(new Error('{"detail":"Email already registered"}'));
    await renderLoaded();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "dup@x.com" } });
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Dup" } });
    fireEvent.change(screen.getByLabelText("Temporary password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /create user/i }));

    expect(await screen.findByText("Email already registered")).toBeTruthy();
    expect(mocks.api.list).toHaveBeenCalledTimes(1); // not reloaded on failure
  });

  it("blocks submit and shows a field error when the display name is blank", async () => {
    await renderLoaded();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "ok@x.com" } });
    fireEvent.change(screen.getByLabelText("Temporary password"), { target: { value: "password123" } });
    // display_name left blank
    fireEvent.click(screen.getByRole("button", { name: /create user/i }));

    expect(await screen.findByText(/Display name is required/i)).toBeTruthy();
    expect(mocks.api.create).not.toHaveBeenCalled();
  });

  it("surfaces a 403 from a role change", async () => {
    mocks.api.setRole.mockRejectedValueOnce(
      new Error('{"detail":"Only an owner can grant the owner role"}'),
    );
    await renderLoaded();
    fireEvent.change(screen.getByLabelText("Role for bob@x.com"), { target: { value: "admin" } });
    expect(await screen.findByText("Only an owner can grant the owner role")).toBeTruthy();
  });

  it("surfaces a delete failure, dismisses the dialog, and does not reload", async () => {
    mocks.api.remove.mockRejectedValueOnce(
      new Error('{"detail":"Cannot remove or demote the last remaining owner"}'),
    );
    await renderLoaded();
    const bobRow = screen.getByText("bob@x.com").closest("tr") as HTMLElement;
    fireEvent.click(within(bobRow).getByRole("button", { name: "Delete" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete user" }));

    expect(await screen.findByText("Cannot remove or demote the last remaining owner")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mocks.api.list).toHaveBeenCalledTimes(1); // not reloaded on failure
  });

  it("shows only the error (no empty table, no 'No users.') when the list fails to load", async () => {
    mocks.api.list.mockReset().mockRejectedValue(new Error('{"detail":"Failed to read users"}'));
    render(<UsersAdmin />);
    expect(await screen.findByText("Failed to read users")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText("No users.")).toBeNull();
  });
});
