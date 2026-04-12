"""DOM snapshot utilities for agent context injection."""

from __future__ import annotations

import re


def rasterize_dom(html: str, max_length: int = 5000) -> str:
    """Convert HTML to a text representation for agent context.

    Strips scripts, styles, and tags. Returns simplified text view of the page.
    """
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_length]


def extract_interactive_elements(html: str) -> list[dict]:
    """Extract buttons, links, inputs, and forms from HTML for agent reference."""
    elements = []

    # Buttons
    for match in re.finditer(r'<button[^>]*>(.*?)</button>', html, re.DOTALL):
        attrs = _extract_attrs(match.group(0))
        elements.append({
            "type": "button",
            "text": re.sub(r'<[^>]+>', '', match.group(1)).strip(),
            **attrs,
        })

    # Links
    for match in re.finditer(r'<a\s[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', html, re.DOTALL):
        elements.append({
            "type": "link",
            "href": match.group(1),
            "text": re.sub(r'<[^>]+>', '', match.group(2)).strip(),
        })

    # Inputs
    for match in re.finditer(r'<input\s[^>]*/?\s*>', html):
        attrs = _extract_attrs(match.group(0))
        elements.append({"type": "input", **attrs})

    return elements[:50]  # limit


def _extract_attrs(tag: str) -> dict:
    """Extract key attributes from an HTML tag."""
    attrs = {}
    for attr in ("id", "name", "class", "type", "placeholder", "value", "aria-label"):
        match = re.search(rf'{attr}=["\']([^"\']*)["\']', tag)
        if match:
            attrs[attr] = match.group(1)
    return attrs
