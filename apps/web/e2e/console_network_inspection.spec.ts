import { test, expect, type ConsoleMessage, type Response } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";
const API_BASE_URL = "http://localhost:8080";
const EVIDENCE_DIR = path.resolve(__dirname, "../../../docs/ui-test-evidence");

interface ConsoleTrace {
  type: string;
  text: string;
  location: {
    url?: string;
    lineNumber?: number;
    columnNumber?: number;
  };
  timestamp: string;
}

interface NetworkRequestTrace {
  url: string;
  method: string;
  status: number;
  headers: Record<string, string>;
  rateLimitLimit?: string;
  rateLimitRemaining?: string;
  timestamp: string;
}

test.describe("Console and Network Inspector E2E", () => {
  const consoleTraces: ConsoleTrace[] = [];
  const networkTraces: NetworkRequestTrace[] = [];
  const unhandledExceptions: string[] = [];
  const consoleWarnings: string[] = [];

  test.beforeEach(async ({ page }) => {
    // Catch browser console logs
    page.on("console", (msg: ConsoleMessage) => {
      const trace: ConsoleTrace = {
        type: msg.type(),
        text: msg.text(),
        location: msg.location(),
        timestamp: new Date().toISOString(),
      };
      consoleTraces.push(trace);

      if (msg.type() === "warning" || msg.type() === "warn") {
        consoleWarnings.push(msg.text());
      }
    });

    // Catch uncaught exceptions
    page.on("pageerror", (err) => {
      unhandledExceptions.push(err.message + "\n" + err.stack);
      consoleTraces.push({
        type: "pageerror",
        text: err.message + "\n" + (err.stack ?? ""),
        location: {},
        timestamp: new Date().toISOString(),
      });
    });

    // Catch network responses
    page.on("response", async (response: Response) => {
      const req = response.request();
      const url = response.url();
      
      // We only care about calls to the backend (i.e. those containing /v1/ or matching API_BASE_URL)
      if (url.includes("/v1/") || url.startsWith(API_BASE_URL)) {
        const headers = await response.allHeaders();
        const trace: NetworkRequestTrace = {
          url,
          method: req.method(),
          status: response.status(),
          headers,
          rateLimitLimit: headers["x-ratelimit-limit"] ?? headers["X-RateLimit-Limit"] ?? headers["x-ratelimit-limit".toLowerCase()],
          rateLimitRemaining: headers["x-ratelimit-remaining"] ?? headers["X-RateLimit-Remaining"] ?? headers["x-ratelimit-remaining".toLowerCase()],
          timestamp: new Date().toISOString(),
        };
        networkTraces.push(trace);
      }
    });
  });

  test("Perform flow and inspect console / network", async ({ page }) => {
    // ── 1. Navigate to /login and dev bypass ──────────────────────────
    await page.goto(`${BASE_URL}/login`);
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();

    const devBypassButton = page.getByRole("button", {
      name: /continue as dev@testlyn\.io/i,
    });
    await expect(devBypassButton).toBeVisible();
    await devBypassButton.click();

    // ── 2. Land on /projects or /onboarding (auto-fallback if zero orgs) ──
    await page.waitForURL(/\/(projects|onboarding)/, { timeout: 20000 });
    
    if (page.url().includes("/onboarding")) {
      console.log("Redirected to onboarding. Creating organization...");
      const orgInput = page.locator("#org-name");
      await expect(orgInput).toBeVisible({ timeout: 10000 });
      await orgInput.fill("Console Network Inspector Org");
      await page.getByRole("button", { name: /create organization/i }).click();
      
      // Now wait for redirection to /projects
      await page.waitForURL(/\/projects/, { timeout: 20000 });
    }

    await expect(page.getByRole("heading", { name: /projects/i })).toBeVisible({ timeout: 15000 });
    
    // Click New Project (use .first() to avoid strict mode violation if empty state CTA is visible)
    const newProjectButton = page.getByRole("button", { name: /new project/i }).first();
    await expect(newProjectButton).toBeVisible({ timeout: 10000 });
    await newProjectButton.click();

    // Fill project name using ID selector
    const projectName = `Console-Net-Audit-${Date.now()}`;
    const nameInput = page.locator("#proj-name");
    await expect(nameInput).toBeVisible({ timeout: 10000 });
    await nameInput.fill(projectName);

    // Click Create Project button
    const createBtn = page.getByRole("button", { name: /create project/i });
    await expect(createBtn).toBeVisible({ timeout: 10000 });
    await createBtn.click();

    // Expect the project to be visible
    await expect(page.getByText(projectName).first()).toBeVisible({ timeout: 15000 });

    // Open project
    await page.getByText(projectName).first().click();
    await page.waitForURL(/\/projects\//, { timeout: 15000 });

    // Let's also do a small wait so the API requests completely resolve and are logged
    await page.waitForTimeout(3000);

    // ── 3. Take a network trace screenshot ────────────────────────────
    // Ensure the folder exists
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    
    // Save screenshot
    await page.screenshot({
      path: path.join(EVIDENCE_DIR, "network_inspection.png"),
      fullPage: true,
    });

    // ── 4. Verify API routes ──────────────────────────────────────────
    // All backend requests should be sent to http://localhost:8080 and be successful
    const apiCalls = networkTraces.filter(t => t.url.includes("/v1/"));
    expect(apiCalls.length).toBeGreaterThan(0);

    console.log(`Verifying ${apiCalls.length} API calls for headers...`);

    for (const call of apiCalls) {
      // 1. Backend API host is localhost:8080
      expect(call.url.startsWith("http://localhost:8080")).toBe(true);

      // 2. Not returning 404 or failing
      expect(call.status).toBeLessThan(400);

      // 3. Confirm presence of rate limit headers
      expect(call.rateLimitLimit).toBeDefined();
      expect(call.rateLimitRemaining).toBeDefined();
    }

    // ── 5. Write console log trace to file ────────────────────────────
    const reportData = {
      unhandledExceptions,
      consoleWarnings,
      consoleTraces,
      networkTraces,
    };
    
    fs.writeFileSync(
      path.join(EVIDENCE_DIR, "console_inspection.json"),
      JSON.stringify(reportData, null, 2)
    );
  });
});
