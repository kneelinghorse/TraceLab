// ABOUTME: Vitest configuration for frontend unit tests.
// ABOUTME: Uses jsdom for React component testing with testing-library.

import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Mirror tsconfig "@/*": ["./src/*"] so component imports resolve under Vitest.
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules", "e2e", "tests"],
    // Specs that render a full page through jsdom spend 50-120 ms on every accessible-name
    // lookup, so a heavy one legitimately needs seconds of CPU. Vitest runs files in parallel,
    // so under load the 5 s default was reporting slow-but-correct specs as failures
    // (CommandPalette, mission-authoring and document-upload each did so in a 20-run soak).
    // Correctness comes from the specs' own explicit waits; this budget only stops a busy
    // machine from manufacturing a red (VERIFY-1, next-step #335).
    testTimeout: 30_000,
  },
});
