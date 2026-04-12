"""Browser test runner -- executes Playwright interaction flows.

Launches a headless browser, runs step-by-step interactions defined in
BrowserTestFlow objects, captures screenshots, console errors, and DOM snapshots.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from devharness.browser_testing.flows import load_flow_from_file
from devharness.core.models import BrowserTestFlow, BrowserTestResult, BrowserTestStep

logger = logging.getLogger(__name__)


class BrowserTestRunner:
    """Execute browser interaction flows using Playwright."""

    def __init__(self, workspace_root: str = ".", artifacts_dir: str | None = None) -> None:
        self._workspace_root = workspace_root
        self._artifacts_dir = artifacts_dir or str(
            Path(workspace_root) / ".devharness" / "artifacts"
        )

    async def run_flow(self, flow: BrowserTestFlow) -> BrowserTestResult:
        """Execute a browser test flow and return results."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return BrowserTestResult(
                flow_name=flow.name,
                passed=False,
                failure_reason="Playwright not installed. Run: pip install playwright && playwright install",
            )

        start_time = time.monotonic()
        console_errors: list[str] = []
        screenshots: list[str] = []
        steps_completed = 0

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": flow.viewport_width, "height": flow.viewport_height}
                )
                page = await context.new_page()

                # Capture console errors
                page.on("console", lambda msg: (
                    console_errors.append(f"{msg.type}: {msg.text}")
                    if msg.type in ("error", "warning")
                    else None
                ))
                page.on("pageerror", lambda err: console_errors.append(f"PageError: {err}"))

                # Navigate to the flow URL
                await page.goto(flow.url, wait_until="networkidle", timeout=30000)

                # Execute steps
                for i, step in enumerate(flow.steps):
                    try:
                        await self._execute_step(page, step)
                        steps_completed = i + 1
                    except Exception as e:
                        # Capture failure screenshot
                        screenshot_path = self._screenshot_path(flow.name, f"failure_step_{i}")
                        await page.screenshot(path=screenshot_path)
                        screenshots.append(screenshot_path)

                        # Get DOM snapshot
                        dom_snapshot = await page.content()
                        dom_text = self._rasterize_dom(dom_snapshot)

                        await browser.close()
                        return BrowserTestResult(
                            flow_name=flow.name,
                            passed=False,
                            steps_completed=steps_completed,
                            steps_total=len(flow.steps),
                            failure_step=i,
                            failure_reason=str(e),
                            screenshots=screenshots,
                            console_errors=console_errors,
                            dom_snapshot=dom_text[:5000],
                            duration_ms=(time.monotonic() - start_time) * 1000,
                        )

                # Run assertions
                for assertion in flow.assertions:
                    await self._check_assertion(page, assertion)

                # Final screenshot
                final_screenshot = self._screenshot_path(flow.name, "final")
                await page.screenshot(path=final_screenshot)
                screenshots.append(final_screenshot)

                await browser.close()

        except Exception as e:
            return BrowserTestResult(
                flow_name=flow.name,
                passed=False,
                failure_reason=f"Browser test error: {e}",
                console_errors=console_errors,
                screenshots=screenshots,
                duration_ms=(time.monotonic() - start_time) * 1000,
            )

        return BrowserTestResult(
            flow_name=flow.name,
            passed=len(console_errors) == 0 or not any("error" in e.lower() for e in console_errors),
            steps_completed=len(flow.steps),
            steps_total=len(flow.steps),
            screenshots=screenshots,
            console_errors=console_errors,
            duration_ms=(time.monotonic() - start_time) * 1000,
        )

    async def run_flow_from_file(self, flow_path: str) -> BrowserTestResult:
        """Load a flow from YAML and execute it."""
        flow = load_flow_from_file(flow_path)
        return await self.run_flow(flow)

    async def _execute_step(self, page, step: BrowserTestStep) -> None:
        """Execute a single browser test step."""
        match step.action:
            case "click":
                await page.click(step.selector, timeout=step.timeout)
            case "fill":
                await page.fill(step.selector, step.value or "", timeout=step.timeout)
            case "wait_for":
                await page.wait_for_selector(step.selector, timeout=step.timeout)
            case "screenshot":
                path = self._screenshot_path("step", step.name or "screenshot")
                await page.screenshot(path=path)
            case "navigate":
                await page.goto(step.value or "", timeout=step.timeout)
            case "type":
                await page.type(step.selector, step.value or "", timeout=step.timeout)
            case "select":
                await page.select_option(step.selector, step.value or "", timeout=step.timeout)
            case "hover":
                await page.hover(step.selector, timeout=step.timeout)
            case "wait":
                import anyio
                await anyio.sleep(step.timeout / 1000)
            case _:
                raise ValueError(f"Unknown action: {step.action}")

    async def _check_assertion(self, page, assertion) -> None:
        """Check a browser test assertion."""
        match assertion.type:
            case "url_contains":
                url = page.url
                if assertion.value not in url:
                    raise AssertionError(f"URL {url} does not contain {assertion.value}")
            case "element_visible":
                elem = await page.query_selector(assertion.selector)
                if elem is None:
                    raise AssertionError(f"Element {assertion.selector} not found")
                if not await elem.is_visible():
                    raise AssertionError(f"Element {assertion.selector} not visible")
            case "no_console_errors":
                # Checked in the result building
                pass
            case "text_contains":
                content = await page.text_content(assertion.selector or "body")
                if assertion.value and assertion.value not in (content or ""):
                    raise AssertionError(
                        f"Text '{assertion.value}' not found in {assertion.selector or 'body'}"
                    )

    def _screenshot_path(self, flow_name: str, step_name: str) -> str:
        """Generate screenshot file path."""
        Path(self._artifacts_dir).mkdir(parents=True, exist_ok=True)
        return str(Path(self._artifacts_dir) / f"{flow_name}_{step_name}.png")

    def _rasterize_dom(self, html: str) -> str:
        """Convert HTML to a text representation for agent context.

        Strips tags and returns a simplified text view of the page.
        """
        import re

        # Remove script and style tags entirely
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        # Replace tags with spaces
        text = re.sub(r"<[^>]+>", " ", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text[:5000]
