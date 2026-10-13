import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Dialog } from "./Dialog";

describe("native dialog close events", () => {
  it("ignores a queued close event after the user has reopened the dialog", () => {
    const onClose = vi.fn();
    const view = render(<Dialog open title="Confirm action" onClose={onClose}>Review</Dialog>);
    const dialog = screen.getByRole("dialog") as HTMLDialogElement;
    view.rerender(<Dialog open={false} title="Confirm action" onClose={onClose}>Review</Dialog>);
    view.rerender(<Dialog open title="Confirm action" onClose={onClose}>Review</Dialog>);

    // Browsers queue close events: the previous close can arrive after showModal.
    fireEvent(dialog, new Event("close"));

    expect(onClose).not.toHaveBeenCalled();
    expect(dialog.open).toBe(true);
  });

  it("still notifies the owner when the native dialog actually closes", () => {
    const onClose = vi.fn();
    render(<Dialog open title="Confirm action" onClose={onClose}>Review</Dialog>);
    const dialog = screen.getByRole("dialog") as HTMLDialogElement;
    dialog.close();
    fireEvent(dialog, new Event("close"));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
