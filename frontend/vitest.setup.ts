// Unmount React trees between tests so component state (e.g. role context)
// never leaks across cases. Vitest globals are enabled, so afterEach exists.
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
