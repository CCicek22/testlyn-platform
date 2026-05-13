"""Checkout step — TS code fragment template."""

from __future__ import annotations


def fragment(
    *,
    cart_selector: str = '[data-testid="cart-button"]',
    checkout_selector: str = '[data-testid="checkout-button"]',
    confirm_selector: str = '[data-testid="order-confirm"]',
) -> str:
    """Return a Playwright TS code fragment for a standard checkout flow."""
    return f"""\
  // --- checkout step ---
  await page.click('{cart_selector}');
  await page.click('{checkout_selector}');
  await page.waitForSelector('{confirm_selector}', {{ timeout: 15000 }});
"""
