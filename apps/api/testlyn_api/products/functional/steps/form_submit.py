"""Form submit step — TS code fragment template."""

from __future__ import annotations


def fragment(
    *,
    form_selector: str = "form",
    submit_selector: str = '[type="submit"]',
    success_selector: str = '[data-testid="success-message"]',
    fields: dict[str, str] | None = None,
) -> str:
    """Return a Playwright TS code fragment for a generic form submission."""
    fill_lines = ""
    if fields:
        for selector, value in fields.items():
            fill_lines += f"  await page.fill('{selector}', '{value}');\n"

    return f"""\
  // --- form submit step ---
  await page.waitForSelector('{form_selector}');
{fill_lines}  await page.click('{submit_selector}');
  await page.waitForSelector('{success_selector}', {{ timeout: 10000 }});
"""
