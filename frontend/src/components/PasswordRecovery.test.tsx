import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { PasswordRecovery } from "@/components/PasswordRecovery";
import { HttpError } from "@/lib/api/http";
import { recoveryBootstrapScript } from "@/lib/auth/recovery";

const mocks = vi.hoisted(() => ({ logout: vi.fn(), request: vi.fn(), confirm: vi.fn() }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ logout: mocks.logout }) }));
vi.mock("@/lib/api/auth", () => ({ requestPasswordReset: mocks.request, confirmPasswordReset: mocks.confirm }));

beforeEach(() => {
  vi.resetAllMocks();
  delete window.__traceLabRecoveryToken;
  localStorage.clear();
});

it("removes the fragment before routing, uses memory once, and never persists a reset credential", () => {
  const token = "a".repeat(43);
  history.replaceState({}, "", `/reset-password#token=${token}`);
  window.eval(recoveryBootstrapScript);
  expect(location.hash).toBe("");
  render(<PasswordRecovery resetting />);
  expect(window.__traceLabRecoveryToken).toBeUndefined();
  expect(localStorage.length).toBe(0);
  expect(screen.getByLabelText("New password")).toBeTruthy();
});

it("explains generic success and lets the user retry without implying delivery", async () => {
  mocks.request.mockResolvedValue({ message: "If eligible, instructions will be sent." });
  render(<PasswordRecovery />);
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "user@controlled.org" } });
  fireEvent.click(screen.getByRole("button", { name: "Send reset link" }));
  expect(await screen.findByRole("status")).toHaveTextContent("If eligible");
  fireEvent.click(screen.getByRole("button", { name: "Try another request" }));
  expect(screen.getByLabelText("Email")).toHaveValue("user@controlled.org");
});

it("does not call the API for mismatched passwords and signs out only after successful reset", async () => {
  const token = "b".repeat(43);
  window.__traceLabRecoveryToken = token;
  mocks.confirm.mockResolvedValue({ message: "Password changed. Sign in with your new password." });
  render(<PasswordRecovery resetting />);
  expect(screen.getByText(/API and MCP keys will stop working/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: "fresh-password" } });
  fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "wrong-password" } });
  fireEvent.click(screen.getByRole("button", { name: "Save new password" }));
  expect(screen.getByRole("alert")).toHaveTextContent("same password twice");
  expect(mocks.confirm).not.toHaveBeenCalled();
  expect(mocks.logout).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "fresh-password" } });
  fireEvent.click(screen.getByRole("button", { name: "Save new password" }));
  await waitFor(() => expect(mocks.logout).toHaveBeenCalledTimes(1));
  expect(mocks.confirm).toHaveBeenCalledWith(token, "fresh-password", "fresh-password");
  expect(screen.queryByLabelText("New password")).toBeNull();
  expect(screen.getByRole("link", { name: "Back to sign in" })).toBeTruthy();
});

it.each([
  [new HttpError("secret-bearing server text", 400), "invalid, expired, or already used"],
  [new HttpError("secret-bearing server text", 429), "Too many attempts"],
  [new HttpError("secret-bearing server text", 503), "temporarily unavailable"],
  [new TypeError("offline"), "Check your connection"],
])("shows a safe error and retains an actionable form (%s)", async (error, message) => {
  window.__traceLabRecoveryToken = "c".repeat(43);
  mocks.confirm.mockRejectedValue(error);
  render(<PasswordRecovery resetting />);
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: "fresh-password" } });
  fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "fresh-password" } });
  fireEvent.click(screen.getByRole("button", { name: "Save new password" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(screen.queryByText("secret-bearing server text")).toBeNull();
  expect(mocks.logout).not.toHaveBeenCalled();
  expect(screen.getByRole("link", { name: "Request a new link" })).toBeTruthy();
});

it("offers reopening the email or requesting again when memory was lost", () => {
  render(<PasswordRecovery resetting />);
  expect(screen.getByRole("alert")).toHaveTextContent("Reopen your email link");
  expect(mocks.confirm).not.toHaveBeenCalled();
});
import "@testing-library/jest-dom/vitest";
