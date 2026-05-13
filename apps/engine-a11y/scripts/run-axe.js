#!/usr/bin/env node
/**
 * run-axe.js — Testlyn a11y engine: Playwright + axe-core audit runner
 *
 * Reads audit config from environment:
 *   AUDIT_URLS   — comma-separated list of URLs to audit
 *   MAX_DEPTH    — crawl depth (1 = only listed URLs, 2+ = follow links; default 1)
 *   WCAG_TAGS    — comma-separated axe-core tag filters (default: wcag2a,wcag2aa,wcag21aa,wcag22aa)
 *   RUN_ID       — test run ID (injected by Cloud Run Job)
 *
 * Emits one JSONL line per violation to stdout. Each line:
 * {
 *   "run_id": "...",
 *   "rule_id": "color-contrast",
 *   "impact": "serious",
 *   "html_snippet": "<button ...>",
 *   "dom_path": "html > body > main > button",
 *   "help_url": "https://dequeuniversity.com/...",
 *   "target_url": "https://example.com/page"
 * }
 *
 * The BQ sidecar (parser/axe.py) consumes this JSONL stream and writes
 * SampleEvent rows to BigQuery with product='a11y'.
 */

const { chromium } = require("playwright");
const { AxePuppeteer } = require("@axe-core/playwright");

const RUN_ID = process.env.RUN_ID || "local";
const MAX_DEPTH = parseInt(process.env.MAX_DEPTH || "1", 10);
const WCAG_TAGS = (process.env.WCAG_TAGS || "wcag2a,wcag2aa,wcag21aa,wcag22aa").split(",");

const rawUrls = process.env.AUDIT_URLS || "";
if (!rawUrls) {
  process.stderr.write("AUDIT_URLS is required\n");
  process.exit(1);
}
const seedUrls = rawUrls.split(",").map((u) => u.trim()).filter(Boolean);

/** @param {string} url @param {import('playwright').Page} page */
async function auditPage(url, page) {
  try {
    await page.goto(url, { waitUntil: "networkidle", timeout: 30_000 });
  } catch (err) {
    process.stderr.write(`[warn] goto failed for ${url}: ${err.message}\n`);
    return;
  }

  let results;
  try {
    results = await new AxePuppeteer(page).withTags(WCAG_TAGS).analyze();
  } catch (err) {
    process.stderr.write(`[warn] axe.analyze failed for ${url}: ${err.message}\n`);
    return;
  }

  for (const violation of results.violations) {
    for (const node of violation.nodes) {
      const row = {
        run_id: RUN_ID,
        rule_id: violation.id,
        impact: violation.impact,
        html_snippet: node.html,
        dom_path: node.target ? node.target.join(" > ") : "",
        help_url: violation.helpUrl,
        target_url: url,
      };
      process.stdout.write(JSON.stringify(row) + "\n");
    }
  }
}

/** Collect hrefs on the same origin up to maxDepth links deep. */
async function crawl(browser, seedUrl, depth) {
  const origin = new URL(seedUrl).origin;
  const visited = new Set([seedUrl]);
  const queue = [{ url: seedUrl, d: 0 }];

  while (queue.length > 0) {
    const { url, d } = queue.shift();
    const page = await browser.newPage();
    await auditPage(url, page);

    if (d < depth - 1) {
      try {
        const hrefs = await page.$$eval("a[href]", (els) =>
          els.map((el) => el.href).filter(Boolean)
        );
        for (const href of hrefs) {
          try {
            const candidate = new URL(href);
            if (candidate.origin === origin && !visited.has(candidate.href)) {
              visited.add(candidate.href);
              queue.push({ url: candidate.href, d: d + 1 });
            }
          } catch {
            // non-parseable href — skip
          }
        }
      } catch {
        // page navigation may have changed DOM
      }
    }

    await page.close();
  }
}

(async () => {
  const browser = await chromium.launch({ args: ["--no-sandbox", "--disable-setuid-sandbox"] });

  try {
    for (const url of seedUrls) {
      await crawl(browser, url, MAX_DEPTH);
    }
  } finally {
    await browser.close();
  }
})();
