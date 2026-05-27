import { test, expect } from "@playwright/test";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";
const EVIDENCE_DIR = "./docs/ui-test-evidence";

test.describe("Project Creator - E2E Integration Test", () => {
  test.beforeAll(async () => {
    // 0. Database cleanup to ensure reproducibility
    try {
      execSync(
        `docker compose -f ./infra/docker-compose.dev.yml exec -T postgres psql -U testlyn_api -d testlyn -c "DELETE FROM projects WHERE name = 'UI Team Integration Project';"`
      );
      console.log("Database cleaned up successfully: deleted existing project 'UI Team Integration Project'.");
    } catch (err) {
      console.error("Warning: DB cleanup command failed, proceeding anyway...", err);
    }
  });

  test("Should verify modal, check validations, create project, and view it", async ({ page }) => {
    // Ensure EVIDENCE_DIR exists
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });

    // ── 1. Navigate to /login, click "Continue as dev@testlyn.io" ──
    await page.goto(`${BASE_URL}/login`);
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();

    const devBypassButton = page.getByRole("button", {
      name: /continue as dev@testlyn\.io/i,
    });
    await expect(devBypassButton).toBeVisible();
    await devBypassButton.click();

    // ── 2. Handle potential onboarding or navigate to '/projects' page ──
    const projectsHeading = page.getByRole("heading", { name: /projects/i }).first();
    const onboardingHeading = page.getByRole("heading", { name: /create your organization/i }).first();

    // Wait until either the Projects dashboard or the Onboarding screen is loaded
    await expect(projectsHeading.or(onboardingHeading)).toBeVisible({ timeout: 15_000 });

    if (await onboardingHeading.isVisible()) {
      console.log("Onboarding page detected. Creating a test organization...");
      const orgNameInput = page.locator("#org-name");
      await expect(orgNameInput).toBeVisible();
      await orgNameInput.fill("QA Testing Org");

      const createOrgButton = page.getByRole("button", { name: /create organization/i });
      await expect(createOrgButton).toBeVisible();
      await createOrgButton.click();

      // Wait to be redirected to /projects after creation
      await page.waitForURL(/\/projects/, { timeout: 15_000 });
      await expect(projectsHeading).toBeVisible({ timeout: 10_000 });
    }

    // Use .first() to avoid strictness violation when empty state button is also visible
    const newProjectButton = page.getByRole("button", { name: /new project/i }).first();
    await expect(newProjectButton).toBeVisible();
    await newProjectButton.click();

    // ── 3. Verify that the creation modal opens correctly ──
    const dialogTitle = page.getByRole("heading", { name: /new project/i }).first();
    await expect(dialogTitle).toBeVisible();

    const nameInput = page.locator("#proj-name");
    await expect(nameInput).toBeVisible();
    await expect(nameInput).toHaveAttribute("required", "");

    const descInput = page.locator("#proj-desc");
    await expect(descInput).toBeVisible();

    const createButton = page.getByRole("button", { name: /create project/i });
    await expect(createButton).toBeVisible();

    // Validate that Create button is initially disabled (empty name validation)
    await expect(createButton).toBeDisabled();

    // Try filling name with spaces and check if it remains disabled
    await nameInput.fill("   ");
    await expect(createButton).toBeDisabled();

    // Capture visual evidence of the creation modal
    const modalPath = path.join(EVIDENCE_DIR, "project_creator_modal.png");
    await page.screenshot({ path: modalPath, fullPage: false });
    console.log(`Saved screenshot of creation modal to ${modalPath}`);

    // ── 4. Enter the project name "UI Team Integration Project" and click Create ──
    await nameInput.fill("UI Team Integration Project");
    await expect(createButton).toBeEnabled();

    // Optionally fill description
    await descInput.fill("Project created automatically by UI Testing Team.");

    // Submit
    await createButton.click();

    // ── 5. Verify that the new project is successfully rendered in the projects dashboard ──
    const newProjectCard = page.getByText("UI Team Integration Project");
    await expect(newProjectCard).toBeVisible({ timeout: 10_000 });

    // ── 6. Click into the new project and verify that the "New test" button is visible ──
    await newProjectCard.click();
    await page.waitForURL(/\/projects\/[0-9a-f-]+/);

    const newTestButton = page.getByRole("button", { name: /new test/i });
    await expect(newTestButton).toBeVisible({ timeout: 10_000 });

    // ── 7. Capture screenshot of the project view ──
    const viewPath = path.join(EVIDENCE_DIR, "project_creator_view.png");
    await page.screenshot({ path: viewPath, fullPage: true });
    console.log(`Saved screenshot of project view to ${viewPath}`);
  });
});
