import { defineConfig } from "cypress";

export default defineConfig({
  video: false,
  retries: 1,
  e2e: {
    baseUrl: process.env.CYPRESS_BASE_URL || "http://localhost:3000",
    specPattern: "cypress/e2e/**/*.cy.ts",
    supportFile: "cypress/support/e2e.ts",
  },
});
