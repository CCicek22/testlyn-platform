import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";
const EVIDENCE_DIR = path.resolve(__dirname, "../../../docs/ui-test-evidence");

// A helper to calculate relative luminance of an RGB/RGBA string
function getLuminance(r: number, g: number, b: number): number {
  const [rs, gs, bs] = [r / 255, g / 255, b / 255].map((c) => {
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
}

// Convert Lightness (L) in CIELAB/oklch to relative luminance (Y)
function lightnessToLuminance(L: number, isPercent: boolean = false): number {
  const normalizedL = isPercent ? L : L; // L is usually 0 to 100 in lab
  // Formula: Y = ((L + 16) / 116)^3
  if (normalizedL <= 8) {
    return normalizedL / 903.3;
  }
  return Math.pow((normalizedL + 16) / 116, 3);
}

// A helper to parse various color formats (RGB, RGBA, LAB, OKLCH)
function getLuminanceFromStr(colorStr: string): number {
  // Check for rgb / rgba
  const rgbMatch = colorStr.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
  if (rgbMatch) {
    const r = parseInt(rgbMatch[1], 10);
    const g = parseInt(rgbMatch[2], 10);
    const b = parseInt(rgbMatch[3], 10);
    return getLuminance(r, g, b);
  }

  // Check for lab(L a b)
  const labMatch = colorStr.match(/lab\(([\d.]+)(?:\s+|,\s*)([\d.-]+)(?:\s+|,\s*)([\d.-]+)\)/);
  if (labMatch) {
    const L = parseFloat(labMatch[1]);
    return lightnessToLuminance(L, false);
  }

  // Check for oklch(L c h) or oklab(L a b)
  const oklchMatch = colorStr.match(/ok(?:lch|lab)\(([\d.]+)(?:\s+|,\s*)([\d.-]+)(?:\s+|,\s*)([\d.-]+)\)/);
  if (oklchMatch) {
    const L = parseFloat(oklchMatch[1]);
    // In oklch/oklab, L is usually a fraction 0 to 1
    const L100 = L <= 1.0 ? L * 100 : L;
    return lightnessToLuminance(L100, false);
  }

  console.log(`Failed to parse color string: "${colorStr}". Defaulting luminance to 0.5`);
  return 0.5;
}

// Calculate contrast ratio between two colors
function getContrastRatio(fgStr: string, bgStr: string): number {
  const l1 = getLuminanceFromStr(fgStr);
  const l2 = getLuminanceFromStr(bgStr);

  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

test.describe("Testlyn Accessibility Audit", () => {
  test.beforeAll(() => {
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  });

  test("Run accessibility checks on Login, Projects, and Onboarding layouts", async ({ page }) => {
    console.log("=== STARTING ACCESSIBILITY AUDIT ===");
    const auditResults: any = {
      login: {},
      onboarding: {},
      projects: {},
      violations: [] as string[],
    };

    // ── MOCK ZERO MEMBERSHIPS AT START ─────────────────────────────────────────
    let currentMemberships: any[] = [];
    
    await page.route("**/v1/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "dev-user-id",
          email: "dev@testlyn.io",
          memberships: currentMemberships,
        }),
      });
    });

    await page.route("**/v1/orgs/mock-org-id/projects", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    // ── 1. AUDIT LOGIN SCREEN ──────────────────────────────────────────────────
    console.log("Navigating to Login Page...");
    await page.goto(`${BASE_URL}/login`);
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();

    // Audit Semantic Layout Tags
    const loginSemantics = await page.evaluate(() => {
      const main = document.querySelector("main") ? "present" : "missing";
      const header = document.querySelector("header") ? "present" : "missing";
      const footer = document.querySelector("footer") ? "present" : "missing";
      const h1s = Array.from(document.querySelectorAll("h1")).map(h => h.innerText.trim());
      return { main, header, footer, h1s };
    });
    auditResults.login.semantics = loginSemantics;

    if (loginSemantics.main === "missing") {
      auditResults.violations.push("Login page: Missing a semantic <main> landmark element.");
    }
    if (loginSemantics.h1s.length === 0) {
      auditResults.violations.push("Login page: Missing a first-level heading <h1>.");
    }

    // Check dev bypass button focus outline and contrast
    const devBypassBtn = page.getByRole("button", { name: /continue as dev@testlyn\.io/i });
    await expect(devBypassBtn).toBeVisible();
    await devBypassBtn.focus();
    
    // Measure dev bypass button contrast
    const btnStyles = await devBypassBtn.evaluate((el) => {
      const style = window.getComputedStyle(el);
      return {
        color: style.color,
        backgroundColor: style.backgroundColor,
        outlineStyle: style.outlineStyle,
        outlineWidth: style.outlineWidth,
        outlineColor: style.outlineColor,
        border: style.border,
        boxShadow: style.boxShadow,
      };
    });

    const ratio = getContrastRatio(btnStyles.color, btnStyles.backgroundColor);
    auditResults.login.devBypassContrast = ratio;
    console.log(`Dev bypass button contrast ratio: ${ratio.toFixed(2)}:1`);

    if (ratio < 4.5) {
      auditResults.violations.push(`Login page: Dev bypass button has low contrast ratio of ${ratio.toFixed(2)}:1 (WCAG AA requires 4.5:1).`);
    }

    // Check focus indicator on the bypass button
    const hasFocusRing = btnStyles.outlineStyle !== "none" || btnStyles.boxShadow.includes("rgb") || btnStyles.border !== "none";
    auditResults.login.devBypassHasFocusRing = hasFocusRing;
    
    // Save screenshot for focus state evidence
    await page.screenshot({
      path: path.join(EVIDENCE_DIR, "a11y_audit_focus.png"),
    });
    console.log("Saved Login / Focus screen evidence to a11y_audit_focus.png");

    // Click the dev bypass. Since currentMemberships = [], we will redirect to onboarding!
    await devBypassBtn.click();

    // ── 2. AUDIT ONBOARDING SCREEN ─────────────────────────────────────────────
    console.log("Waiting for navigation to onboarding...");
    await page.waitForURL(/\/onboarding/, { timeout: 10_000 });
    await expect(page.getByRole("heading", { name: /create your organization/i })).toBeVisible();
    console.log("Successfully landed on Onboarding layout!");

    // Audit Semantic Layout Tags
    const onboardingSemantics = await page.evaluate(() => {
      const main = document.querySelector("main") ? "present" : "missing";
      const h1s = Array.from(document.querySelectorAll("h1")).map(h => h.innerText.trim());
      const hasOrgNameLabel = !!document.querySelector('label[for="org-name"]');
      const orgInput = document.querySelector("#org-name");
      
      return {
        main,
        h1s,
        hasOrgNameLabel,
        hasOrgNameId: !!orgInput,
        placeholder: orgInput ? orgInput.getAttribute("placeholder") : null,
      };
    });
    auditResults.onboarding.semantics = onboardingSemantics;

    if (onboardingSemantics.main === "missing") {
      auditResults.violations.push("Onboarding layout: Missing a semantic <main> landmark element.");
    }
    if (!onboardingSemantics.hasOrgNameLabel) {
      auditResults.violations.push("Onboarding layout: '#org-name' input is missing a corresponding semantic <label> element.");
    }

    // Check contrast for text
    const textContrastStyles = await page.evaluate(() => {
      const subtext = document.querySelector(".text-zinc-400") || document.querySelector("p");
      if (!subtext) return null;
      const style = window.getComputedStyle(subtext);
      return {
        color: style.color,
        backgroundColor: style.backgroundColor,
      };
    });

    if (textContrastStyles) {
      let bgColor = textContrastStyles.backgroundColor;
      if (bgColor === "rgba(0, 0, 0, 0)" || bgColor === "transparent") {
        bgColor = "rgb(10, 10, 11)"; // Default Testlyn dark mode surface background
      }
      
      const subtextRatio = getContrastRatio(textContrastStyles.color, bgColor);
      auditResults.onboarding.subtextContrast = subtextRatio;
      console.log(`Onboarding subtext contrast ratio: ${subtextRatio.toFixed(2)}:1`);
      if (subtextRatio < 4.5) {
        auditResults.violations.push(`Onboarding layout: Subtext has low contrast ratio of ${subtextRatio.toFixed(2)}:1 (WCAG AA requires 4.5:1).`);
      }
    }

    // ── 3. TRANSITION TO PROJECTS DASHBOARD ────────────────────────────────────
    console.log("Mocking organization membership transition...");
    currentMemberships = [
      {
        org_id: "mock-org-id",
        role: "admin",
        org: { id: "mock-org-id", name: "Mock Org" },
      },
    ];

    // Trigger membership refetch by navigating or triggering something.
    await page.route("**/v1/orgs", async (route) => {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ id: "mock-org-id", name: "Mock Org" }),
      });
    });

    await page.locator("#org-name").fill("Audit Organization");
    await page.getByRole("button", { name: /create organization/i }).click();

    // Wait to land on /projects page
    console.log("Waiting for navigation to Projects dashboard...");
    await page.waitForURL(/\/projects/, { timeout: 15_000 });
    await expect(page.getByRole("heading", { name: /projects/i })).toBeVisible();
    console.log("Successfully landed on Projects layout!");

    // Audit Semantic Layout Tags
    const projectsSemantics = await page.evaluate(() => {
      const main = document.querySelector("main") ? "present" : "missing";
      const header = document.querySelector("header") ? "present" : "missing";
      const footer = document.querySelector("footer") ? "present" : "missing";
      const nav = document.querySelector("nav") ? "present" : "missing";
      const h1s = Array.from(document.querySelectorAll("h1")).map(h => h.innerText.trim());
      return { main, header, footer, nav, h1s };
    });
    auditResults.projects.semantics = projectsSemantics;

    if (projectsSemantics.main === "missing") {
      auditResults.violations.push("Projects dashboard: Missing a semantic <main> landmark element.");
    }
    if (projectsSemantics.nav === "missing") {
      auditResults.violations.push("Projects dashboard: Missing a semantic <nav> navigation element.");
    }

    // Find the "New project" button, focus it, and check keyboard focus indicator
    const newProjectBtn = page.getByRole("button", { name: /new project/i }).first();
    await newProjectBtn.focus();

    // Check New Project Button styles
    const newProjectBtnStyles = await newProjectBtn.evaluate((el) => {
      const style = window.getComputedStyle(el);
      return {
        color: style.color,
        backgroundColor: style.backgroundColor,
        outlineStyle: style.outlineStyle,
        outlineWidth: style.outlineWidth,
        outlineColor: style.outlineColor,
        border: style.border,
        boxShadow: style.boxShadow,
      };
    });
    console.log("New Project Button Styles (focused):", newProjectBtnStyles);
    
    let btnBgColor = newProjectBtnStyles.backgroundColor;
    if (btnBgColor === "rgba(0, 0, 0, 0)" || btnBgColor === "transparent") {
      btnBgColor = "rgb(10, 10, 11)";
    }
    const projectsBtnRatio = getContrastRatio(newProjectBtnStyles.color, btnBgColor);
    auditResults.projects.btnContrast = projectsBtnRatio;
    console.log(`New Project Button Contrast Ratio: ${projectsBtnRatio.toFixed(2)}:1`);

    if (projectsBtnRatio < 4.5) {
      auditResults.violations.push(`Projects dashboard: 'New project' button has low contrast ratio of ${projectsBtnRatio.toFixed(2)}:1 (WCAG AA requires 4.5:1).`);
    }

    // Check if a keyboard focus ring is present
    const projectsHasFocusRing = newProjectBtnStyles.outlineStyle !== "none" || newProjectBtnStyles.boxShadow.includes("rgb") || newProjectBtnStyles.border !== "none";
    auditResults.projects.newProjectBtnHasFocusRing = projectsHasFocusRing;

    // Save screenshot for projects focus state evidence
    await page.screenshot({
      path: path.join(EVIDENCE_DIR, "a11y_audit_projects.png"),
    });
    console.log("Saved Projects screen evidence to a11y_audit_projects.png");

    // Check custom UI elements for clear ARIA attributes
    const buttonsWithAria = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll("button"));
      return btns.map(b => ({
        text: b.innerText.trim(),
        ariaLabel: b.getAttribute("aria-label"),
        ariaExpanded: b.getAttribute("aria-expanded"),
        hasAriaHiddenIcon: !!b.querySelector('svg[aria-hidden="true"]'),
      }));
    });
    auditResults.projects.buttonsWithAria = buttonsWithAria;

    // Output findings JSON to evidence dir
    fs.writeFileSync(
      path.join(EVIDENCE_DIR, "a11y_audit_results.json"),
      JSON.stringify(auditResults, null, 2)
    );
    console.log("Accessibility Audit completed successfully. Results saved to docs/ui-test-evidence/a11y_audit_results.json");
  });
});
