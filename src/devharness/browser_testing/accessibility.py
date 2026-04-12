"""Basic accessibility checks for browser tests."""

from __future__ import annotations

import re


async def check_accessibility(page) -> list[dict]:
    """Run basic accessibility checks on a Playwright page.

    Returns a list of issues found.
    """
    issues: list[dict] = []

    try:
        # Check for images without alt text
        images = await page.query_selector_all("img:not([alt])")
        for img in images:
            src = await img.get_attribute("src") or "unknown"
            issues.append({
                "type": "missing_alt",
                "severity": "warning",
                "message": f"Image without alt text: {src[:100]}",
            })

        # Check for inputs without labels
        inputs = await page.query_selector_all("input:not([aria-label]):not([id])")
        for inp in inputs:
            name = await inp.get_attribute("name") or "unknown"
            issues.append({
                "type": "missing_label",
                "severity": "warning",
                "message": f"Input without label or aria-label: {name}",
            })

        # Check for empty buttons
        buttons = await page.query_selector_all("button")
        for btn in buttons:
            text = (await btn.text_content() or "").strip()
            aria = await btn.get_attribute("aria-label") or ""
            if not text and not aria:
                issues.append({
                    "type": "empty_button",
                    "severity": "error",
                    "message": "Button with no text or aria-label",
                })

        # Check page title
        title = await page.title()
        if not title:
            issues.append({
                "type": "missing_title",
                "severity": "warning",
                "message": "Page has no title",
            })

    except Exception:
        pass  # a11y checks should never break the test

    return issues
