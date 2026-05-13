"""Payment step — TS code fragment template."""

from __future__ import annotations


def fragment(
    *,
    card_number_selector: str = '[data-testid="card-number"]',
    expiry_selector: str = '[data-testid="card-expiry"]',
    cvc_selector: str = '[data-testid="card-cvc"]',
    pay_selector: str = '[data-testid="pay-button"]',
    success_selector: str = '[data-testid="payment-success"]',
    test_card: str = "4242424242424242",
) -> str:
    """Return a Playwright TS code fragment for a Stripe-style payment flow."""
    return f"""\
  // --- payment step ---
  await page.fill('{card_number_selector}', '{test_card}');
  await page.fill('{expiry_selector}', '12/30');
  await page.fill('{cvc_selector}', '123');
  await page.click('{pay_selector}');
  await page.waitForSelector('{success_selector}', {{ timeout: 20000 }});
"""
