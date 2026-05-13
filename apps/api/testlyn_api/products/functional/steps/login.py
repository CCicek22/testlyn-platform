"""Login step — TS code fragment template."""

from __future__ import annotations


def fragment(
    *,
    email_selector: str = '[data-testid="email"]',
    password_selector: str = '[data-testid="password"]',
    submit_selector: str = '[data-testid="login-submit"]',
    success_selector: str = '[data-testid="dashboard"]',
) -> str:
    """Return a Playwright TS code fragment for a standard login flow."""
    return f"""\
  // --- login step ---
  await page.fill('{email_selector}', credentials.email);
  await page.fill('{password_selector}', credentials.password);
  await page.click('{submit_selector}');
  await page.waitForSelector('{success_selector}', {{ timeout: 10000 }});
"""
