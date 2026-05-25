import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for Testlyn web e2e.
 *
 * Assumes a LOCAL full stack already running (no managed webServer):
 *   - web  at http://localhost:3000  (NEXT_PUBLIC_DEV_AUTH_BYPASS=false, real Firebase)
 *   - api  at http://localhost:8080  (RUN_MODE=docker, dev_auth_bypass=false, FIREBASE_PROJECT_ID=example-project)
 *   - postgres + redis via infra/docker-compose.dev.yml (migrations applied)
 *
 * Override host via PLAYWRIGHT_BASE_URL.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
