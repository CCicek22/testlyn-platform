import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";
const EVIDENCE_DIR = path.resolve(__dirname, "../../../docs/ui-test-evidence");

test.describe("Visual Audit — Login and Projects Flow", () => {
  const consoleErrors: string[] = [];
  const consoleMessages: string[] = [];

  test.beforeEach(async ({ page }) => {
    // Collect console logs and errors
    page.on("console", (msg) => {
      const text = `[${msg.type()}] ${msg.text()}`;
      consoleMessages.push(text);
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    // Ensure visual evidence folder exists
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  });

  test.afterEach(async () => {
    // Print collected console logs or errors for reporting
    if (consoleErrors.length > 0) {
      console.error("Collected console errors during test:", consoleErrors);
    }
  });

  test("visual audit and bypass authentication flow", async ({ page }) => {
    // 1. Navigate to the login page
    console.log(`Navigating to ${BASE_URL}/login...`);
    await page.goto(`${BASE_URL}/login`);

    // Verify page title and header
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();

    // Take screenshot of Login page
    const loginScreenshotPath = path.join(EVIDENCE_DIR, "visual_audit_login.png");
    await page.screenshot({ path: loginScreenshotPath, fullPage: true });
    console.log(`Saved login screenshot to ${loginScreenshotPath}`);

    // 2. Verify "Continue as dev@testlyn.io" button is visible and active
    const devBypassButton = page.getByRole("button", {
      name: /continue as dev@testlyn\.io/i,
    });
    await expect(devBypassButton).toBeVisible();
    await expect(devBypassButton).toBeEnabled();

    // 3. Click the button to log in using the dev bypass authentication
    console.log("Clicking the dev bypass authentication button...");
    await devBypassButton.click();

    // 4. Verify that you land successfully on the '/projects' page or need onboarding first.
    // Since Next.js does a client-side redirect, we wait for either header element to appear.
    const projectsHeader = page.getByRole("heading", { name: /projects/i });
    const onboardingHeader = page.getByRole("heading", { name: /create your organization/i });

    console.log("Waiting to see which page settles...");
    const settledPage = await Promise.race([
      projectsHeader.waitFor({ state: "visible", timeout: 10_000 }).then(() => "projects"),
      onboardingHeader.waitFor({ state: "visible", timeout: 10_000 }).then(() => "onboarding")
    ]);

    console.log(`Settled on screen: ${settledPage}`);

    if (settledPage === "onboarding") {
      console.log("Fresh database detected (no memberships). Performing quick onboarding...");
      const orgNameInput = page.locator("#org-name");
      await expect(orgNameInput).toBeVisible();
      await orgNameInput.fill("Visual Audit Org");

      const createOrgBtn = page.getByRole("button", { name: /create organization/i });
      await expect(createOrgBtn).toBeVisible();
      await createOrgBtn.click();

      console.log("Waiting for redirect to /projects...");
      await page.waitForURL(/\/projects/, { timeout: 15_000 });
      await expect(projectsHeader).toBeVisible();
    }

    expect(new URL(page.url()).pathname).toBe("/projects");

    console.log(`Current page URL is: ${page.url()}`);

    await expect(projectsHeader).toBeVisible();

    // Wait for content to render completely
    await page.waitForTimeout(1000);

    // Take screenshot of Projects page
    const projectsScreenshotPath = path.join(EVIDENCE_DIR, "visual_audit_projects.png");
    await page.screenshot({ path: projectsScreenshotPath, fullPage: true });
    console.log(`Saved projects screenshot to ${projectsScreenshotPath}`);

    // Print all gathered console details for visual analysis
    console.log("Console errors detected:", consoleErrors);
    console.log("Total console messages logged:", consoleMessages.length);
  });
});
