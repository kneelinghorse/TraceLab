import { defineConfig, devices } from "@playwright/test";
import path from "path";

const port = Number(process.env.PLAYWRIGHT_PORT || 3100);
const baseURL = process.env.PLAYWRIGHT_BASE_URL || `http://127.0.0.1:${port}`;
const skipServer = ["1", "true"].includes(String(process.env.PLAYWRIGHT_SKIP_SERVER).toLowerCase());

const repoRoot = path.resolve(__dirname, "..");
const telemetryReporterPath = path.resolve(repoRoot, "cmos/scripts/playwright_telemetry_reporter.js");
const telemetryOutputPath = process.env.PLAYWRIGHT_TELEMETRY_OUTPUT
  ? path.resolve(process.env.PLAYWRIGHT_TELEMETRY_OUTPUT)
  : path.resolve(repoRoot, "telemetry/events/.artifacts/playwright-latest.json");
const baseReporter = process.env.CI ? "github" : "list";
const reporters: any = [
  [baseReporter],
  [telemetryReporterPath, { output: telemetryOutputPath, repoRoot }],
];

const webServer = skipServer
  ? undefined
  : {
      command: `npm run dev -- --hostname 0.0.0.0 --port ${port}`,
      url: baseURL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    };

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  reporter: reporters,
  use: {
    baseURL,
    trace: "on-first-retry",
    video: "off",
  },
  webServer,
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
