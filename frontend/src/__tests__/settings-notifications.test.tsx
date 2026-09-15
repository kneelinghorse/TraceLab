import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ get: vi.fn(), update: vi.fn() }));
vi.mock("@/components/AuthGate", () => ({ AuthGate: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock("@/components/ThemeSelect", () => ({ ThemeSelect: () => null }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isReady: true, isAuthenticated: true, user: { user_id: "owner", email: "owner@example.test", display_name: "Owner" } }) }));
vi.mock("@/lib/api/settings", () => ({
  profileApi: { get: mocks.get, update: mocks.update },
  apiKeysApi: { list: vi.fn().mockResolvedValue({ keys: [] }), create: vi.fn(), delete: vi.fn() },
  inviteCodesApi: { list: vi.fn().mockResolvedValue({ codes: [] }), create: vi.fn(), delete: vi.fn() },
}));
import SettingsPage from "@/pages/settings";

const profile = (enabled: boolean) => ({ user_id: "owner", email: "owner@example.test", display_name: "Owner", role: "member", email_notifications_enabled: enabled });

async function openSettings() {
  await act(async () => { render(<SettingsPage />); });
}

describe("mission email preference on Settings", () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.update.mockReset();
  });

  it("shows the stored preference and then whatever the server saved", async () => {
    mocks.get.mockResolvedValue(profile(true));
    mocks.update.mockResolvedValue(profile(false));
    await openSettings();
    const toggle = await screen.findByRole("checkbox", { name: "Mission emails" });
    expect(toggle).toBeChecked();
    fireEvent.click(toggle);
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith({ email_notifications_enabled: false }));
    expect(await screen.findByText("Mission emails are off")).toBeVisible();
    expect(screen.getByRole("checkbox", { name: "Mission emails" })).not.toBeChecked();
  });

  it("keeps the stored preference when saving fails", async () => {
    mocks.get.mockResolvedValue(profile(true));
    mocks.update.mockRejectedValue(new Error("Network unavailable"));
    await openSettings();
    fireEvent.click(await screen.findByRole("checkbox", { name: "Mission emails" }));
    expect(await screen.findByText("Network unavailable")).toBeVisible();
    expect(screen.getByRole("checkbox", { name: "Mission emails" })).toBeChecked();
  });

  it("says the preference could not be loaded instead of showing a guessed value", async () => {
    mocks.get.mockRejectedValue(new Error("offline"));
    await openSettings();
    expect(await screen.findByText("Could not load your notification preference.")).toBeVisible();
    expect(screen.queryByRole("checkbox", { name: "Mission emails" })).toBeNull();
  });
});
