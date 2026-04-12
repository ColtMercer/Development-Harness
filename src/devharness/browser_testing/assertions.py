"""Browser test assertion checkers."""

from __future__ import annotations

from devharness.core.models import BrowserAssertion


async def check_assertion(page, assertion: BrowserAssertion) -> tuple[bool, str]:
    """Check an assertion against a Playwright page. Returns (passed, message)."""
    try:
        match assertion.type:
            case "url_contains":
                url = page.url
                if assertion.value and assertion.value in url:
                    return True, f"URL contains '{assertion.value}'"
                return False, f"URL '{url}' does not contain '{assertion.value}'"

            case "element_visible":
                elem = await page.query_selector(assertion.selector)
                if elem and await elem.is_visible():
                    return True, f"Element {assertion.selector} is visible"
                return False, f"Element {assertion.selector} is not visible"

            case "no_console_errors":
                return True, "Console error check deferred to result"

            case "text_contains":
                content = await page.text_content(assertion.selector or "body")
                if assertion.value and assertion.value in (content or ""):
                    return True, f"Text '{assertion.value}' found"
                return False, f"Text '{assertion.value}' not found"

            case _:
                return False, f"Unknown assertion type: {assertion.type}"
    except Exception as e:
        return False, f"Assertion error: {e}"
