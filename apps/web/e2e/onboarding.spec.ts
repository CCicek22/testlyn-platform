/**
 * Create-org onboarding E2E — verifies the zero-membership onboarding flow.
 *
 * Requires a LOCAL full stack (real Firebase auth, NOT dev-bypass):
 *   - web at :3000 with NEXT_PUBLIC_DEV_AUTH_BYPASS=false + real NEXT_PUBLIC_FIREBASE_*
 *   - api at :8080 with dev_auth_bypass=false, FIREBASE_PROJECT_ID=example-project, fresh DB
 *
 * A throwaway Firebase user is created via the Identity Toolkit REST API in
 * beforeAll, so the fresh local DB holds zero memberships for that user →
 * triggers the onboarding redirect.
 *
 * Run: pnpm exec playwright test e2e/onboarding.spec.ts
 */

import { test, expect, type Page, type ConsoleMessage } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const FIREBASE_API_KEY =
  process.env["FIREBASE_WEB_API_KEY"] ??
  "mock-firebase-api-key-placeholder";

const EVIDENCE_DIR = path.resolve(
  __dirname,
  "../../../docs/ui-test-evidence/onboarding"
);

const EMAIL = `onb-e2e-${Date.now()}-${Math.floor(Math.random() * 1e4)}@example.com`;
const PASSWORD = process.env["E2E_PASSWORD"] ?? "change-me-e2e";

let page: Page;
const consoleErrors: string[] = [];

async function shot(name: string) {
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.screenshot({
    path: path.join(EVIDENCE_DIR, `${name}.png`),
    fullPage: true,
  });
}

test.describe.serial("Create-org onboarding (zero-membership user)", () => {
  test.beforeAll(async ({ browser }) => {
    // 1. Provision a brand-new Firebase user (zero memberships in the fresh DB).
    const res = await fetch(
      `https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=${FIREBASE_API_KEY}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: EMAIL,
          password: PASSWORD,
          returnSecureToken: true,
        }),
      }
    );
    const body = await res.json();
    if (!res.ok) {
      throw new Error(`Firebase signUp failed: ${JSON.stringify(body)}`);
    }

    const context = await browser.newContext();
    page = await context.newPage();

    page.on("console", (msg: ConsoleMessage) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });
  });

  test.afterAll(async () => {
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    fs.writeFileSync(
      path.join(EVIDENCE_DIR, "console-errors.json"),
      JSON.stringify({ email: EMAIL, consoleErrors }, null, 2)
    );
    await page.context().close();
  });

  // ── Case 1: fresh zero-org user is redirected to /onboarding ────────────────
  test("zero-membership user lands on /onboarding (not the dashboard)", async () => {
    await page.goto("/login");
    await expect(
      page.getByRole("heading", { name: /sign in/i })
    ).toBeVisible();
    await shot("01-login");

    await page.locator("#email").fill(EMAIL);
    await page.locator("#password").fill(PASSWORD);
    await page.getByRole("button", { name: /^sign in$/i }).click();

    // login-form pushes /projects; the dashboard org-guard then redirects a
    // zero-membership user to /onboarding.
    await page.waitForURL(/\/onboarding/, { timeout: 20_000 });
    await expect(
      page.getByRole("heading", { name: /create your organization/i })
    ).toBeVisible();
    await shot("02-onboarding");

    expect(new URL(page.url()).pathname).toBe("/onboarding");
  });

  // ── Case 2: submit org name → POST /v1/orgs 201 → lands on /projects ────────
  test("submitting org name POSTs /v1/orgs (201) and lands on /projects", async () => {
    const orgsPost = page.waitForResponse(
      (r) =>
        r.url().includes("/v1/orgs") && r.request().method() === "POST",
      { timeout: 20_000 }
    );

    await page.locator("#org-name").fill("Onboarding QA Org");
    await page.getByRole("button", { name: /create organization/i }).click();

    const resp = await orgsPost;
    expect(resp.status()).toBe(201);

    await page.waitForURL(/\/projects/, { timeout: 20_000 });
    await shot("03-projects-after-create");
    expect(new URL(page.url()).pathname).toBe("/projects");
  });

  // ── Case 3: an org'd user visiting /onboarding bounces to /projects ─────────
  test("org'd user visiting /onboarding bounces to /projects", async () => {
    await page.goto("/onboarding");
    await page.waitForURL(/\/projects/, { timeout: 20_000 });
    await shot("04-onboarding-bounce");
    expect(new URL(page.url()).pathname).toBe("/projects");
  });
});
