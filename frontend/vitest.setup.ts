// Unmount React trees between tests so component state (e.g. role context)
// never leaks across cases. Vitest globals are enabled, so afterEach exists.
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom supplies the element but not the browser's modal methods. Browser
// regressions separately exercise focus trapping, Escape and focus return.
HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };

afterEach(() => {
  cleanup();
});
