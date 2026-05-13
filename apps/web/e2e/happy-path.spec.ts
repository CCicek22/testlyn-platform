/**
 * Testlyn Happy-Path E2E — Phase 1 vertical slice
 *
 * HOW TO ENABLE
 * =============
 * 1. Start the full local stack:
 *      docker compose -f infra/docker-compose.dev.yml up -d
 *      cd apps/api && DATABASE_URL=... uv run alembic upgrade head
 *      cd apps/api && DEV_AUTH_BYPASS=true uv run uvicorn testlyn_api.main:app --host 0.0.0.0 --port 8080
 *      cd apps/web && NEXT_PUBLIC_DEV_AUTH_BYPASS=true pnpm dev
 *
 * 2. Remove `test.describe.skip` (change to `test.describe`) and run:
 *      pnpm exec playwright test e2e/happy-path.spec.ts
 *
 * 3. The test expects the API at http://localhost:8080 and web at http://localhost:3000.
 *    Adjust BASE_URL and API_BASE_URL if your ports differ.
 *
 * KNOWN GAPS (to revisit when stack is fully up):
 * - Step 4 expects /v1/runs/:id/cancel — that endpoint is not yet implemented in the API
 *   (see integration-checker finding #1). The cancel button click will 404 until it is added.
 * - SSE chart population requires the k6 engine container to actually emit BQ rows.
 *   Against a real docker-compose run (profile=engine) this works; against stub API it will
 *   render an empty chart which still passes the chart-container assertion.
 */

import { test, expect } from "@playwright/test";

const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";

const MINIMAL_K6_SCRIPT = `
import http from 'k6/http';
import { sleep } from 'k6';

export const options = { vus: 1, duration: '5s' };

export default function () {
  http.get('https://test.k6.io');
  sleep(1);
}
`.trim();

// Wrapped in skip — remove the `.skip` once the full docker-compose stack is running locally.
// See comment block above for enable instructions.
test.describe.skip("Happy path — dev-bypass login to live chart", () => {
  test("signup → project → test → run → live chart", async ({ page }) => {
    // ── 1. Navigate to /login, click "Continue as dev@testlyn.io" ──────────────
    await page.goto(`${BASE_URL}/login`);
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();

    const devBypassButton = page.getByRole("button", {
      name: /continue as dev@testlyn\.io/i,
    });
    await expect(devBypassButton).toBeVisible();
    await devBypassButton.click();

    // ── 2. Land on /projects, click "New project", fill name, submit ───────────
    await expect(page).toHaveURL(/\/projects/);
    await expect(page.getByRole("heading", { name: /projects/i })).toBeVisible();

    const newProjectButton = page.getByRole("button", { name: /new project/i });
    await expect(newProjectButton).toBeVisible();
    await newProjectButton.click();

    // Dialog / modal should appear
    const nameInput = page.getByLabel(/project name/i);
    await expect(nameInput).toBeVisible();
    await nameInput.fill("Smoke Test Project");

    await page.getByRole("button", { name: /create/i }).click();

    // Project should appear in the list (or redirect to project page)
    await expect(page.getByText("Smoke Test Project")).toBeVisible();

    // ── 3. Open the new project, click "New test", paste k6 script, create ─────
    await page.getByText("Smoke Test Project").click();
    await expect(page).toHaveURL(/\/projects\//);

    await page.getByRole("button", { name: /new test/i }).click();

    const testNameInput = page.getByLabel(/test name/i);
    await expect(testNameInput).toBeVisible();
    await testNameInput.fill("Smoke Load Test");

    // Monaco editor: paste script into the editor contenteditable region
    const monacoEditor = page.locator(".monaco-editor textarea").first();
    await monacoEditor.focus();
    // Select all + replace with our script
    await monacoEditor.press("ControlOrMeta+a");
    await monacoEditor.fill(MINIMAL_K6_SCRIPT);

    await page.getByRole("button", { name: /create test/i }).click();

    await expect(page.getByText("Smoke Load Test")).toBeVisible();

    // ── 4. Click "Run" on the test, navigate to /runs/<id> ────────────────────
    await page.getByRole("button", { name: /run/i }).first().click();

    // API returns TestRun with an id; the page should redirect or navigate to /runs/<id>
    await page.waitForURL(/\/runs\/[0-9a-f-]+/, { timeout: 10_000 });

    const runId = page.url().split("/runs/")[1];
    expect(runId).toBeTruthy();

    // ── 5. Assert live chart container appears and heading shows state badge ───
    // Chart container — LiveLatencyChart renders inside a div with data-testid or class
    const chartContainer = page
      .locator(".recharts-wrapper, [data-testid='live-chart']")
      .first();
    await expect(chartContainer).toBeVisible({ timeout: 10_000 });

    // State badge — should show "Queued" or "Running"
    const stateBadge = page
      .locator("span")
      .filter({ hasText: /queued|running/i })
      .first();
    await expect(stateBadge).toBeVisible({ timeout: 5_000 });
  });
});
