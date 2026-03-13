// ABOUTME: Vitest configuration for frontend unit tests.
// ABOUTME: Uses jsdom for React component testing with testing-library.

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [],
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules", "e2e", "tests"],
  },
});
