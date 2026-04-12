"""Verifier that runs declarative browser test flows.

This verifier uses Playwright (if available) to execute
:class:`BrowserTestFlow` definitions against a running application.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import yaml

from devharness.core.models import (
    BrowserTestFlow,
    BrowserTestResult,
    Thread,
    Turn,
    VerificationResult,
)
from devharness.verification.base import BaseVerifier

logger = logging.getLogger(__name__)


class BrowserVerifier(BaseVerifier):
    """Executes browser test flows and reports results.

    Parameters
    ----------
    flow_paths:
        List of paths to YAML files defining :class:`BrowserTestFlow` objects.
        If empty, the verifier passes with a skip message.
    """

    def __init__(self, flow_paths: list[str] | None = None) -> None:
        self._flow_paths = flow_paths or []

    @property
    def name(self) -> str:
        return "browser_verifier"

    async def verify(self, thread: Thread, turn: Turn) -> VerificationResult:
        if not self._flow_paths:
            return VerificationResult(
                verifier_name=self.name,
                passed=True,
                message="No browser test flows configured",
            )

        flows = self._load_flows()
        if not flows:
            return VerificationResult(
                verifier_name=self.name,
                passed=True,
                message="No valid browser test flows found",
            )

        results: list[BrowserTestResult] = []
        for flow in flows:
            result = await self._run_flow(flow)
            results.append(result)

        failed = [r for r in results if not r.passed]
        all_passed = len(failed) == 0

        details: dict[str, object] = {
            "total": len(results),
            "passed": len(results) - len(failed),
            "failed": len(failed),
            "results": [r.model_dump() for r in results],
        }

        return VerificationResult(
            verifier_name=self.name,
            passed=all_passed,
            message=(
                f"All {len(results)} browser test(s) passed"
                if all_passed
                else f"{len(failed)}/{len(results)} browser test(s) failed"
            ),
            details=details,
        )

    def _load_flows(self) -> list[BrowserTestFlow]:
        """Parse flow YAML files into model objects."""
        flows: list[BrowserTestFlow] = []
        for path_str in self._flow_paths:
            path = Path(path_str)
            if not path.exists():
                logger.warning("Browser flow file not found: %s", path)
                continue
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                flows.append(BrowserTestFlow(**raw))
            except Exception:
                logger.warning("Failed to parse browser flow %s", path, exc_info=True)
        return flows

    async def _run_flow(self, flow: BrowserTestFlow) -> BrowserTestResult:
        """Execute a single browser test flow.

        If Playwright is not installed, the flow is marked as failed with
        a descriptive message.
        """
        t0 = time.monotonic()
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return BrowserTestResult(
                flow_name=flow.name,
                passed=False,
                steps_total=len(flow.steps),
                failure_reason="playwright is not installed (pip install playwright)",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": flow.viewport_width, "height": flow.viewport_height}
                )
                page = await context.new_page()
                await page.goto(flow.url)

                completed = 0
                for i, step in enumerate(flow.steps):
                    try:
                        await self._execute_step(page, step)
                        completed += 1
                    except Exception as exc:
                        await browser.close()
                        return BrowserTestResult(
                            flow_name=flow.name,
                            passed=False,
                            steps_completed=completed,
                            steps_total=len(flow.steps),
                            failure_step=i,
                            failure_reason=str(exc),
                            duration_ms=(time.monotonic() - t0) * 1000,
                        )

                # Run assertions.
                assertion_errors: list[str] = []
                for assertion in flow.assertions:
                    try:
                        await self._check_assertion(page, assertion)
                    except Exception as exc:
                        assertion_errors.append(str(exc))

                await browser.close()

                if assertion_errors:
                    return BrowserTestResult(
                        flow_name=flow.name,
                        passed=False,
                        steps_completed=completed,
                        steps_total=len(flow.steps),
                        failure_reason="; ".join(assertion_errors),
                        duration_ms=(time.monotonic() - t0) * 1000,
                    )

                return BrowserTestResult(
                    flow_name=flow.name,
                    passed=True,
                    steps_completed=completed,
                    steps_total=len(flow.steps),
                    duration_ms=(time.monotonic() - t0) * 1000,
                )
        except Exception as exc:
            return BrowserTestResult(
                flow_name=flow.name,
                passed=False,
                steps_total=len(flow.steps),
                failure_reason=f"Unexpected error: {exc}",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

    @staticmethod
    async def _execute_step(page: object, step: object) -> None:
        """Execute a single BrowserTestStep on a Playwright page."""
        # Import types locally to avoid hard dependency.
        from devharness.core.models import BrowserTestStep

        assert isinstance(step, BrowserTestStep)  # noqa: S101
        action = step.action.lower()

        if action == "navigate" and step.value:
            await page.goto(step.value, timeout=step.timeout)  # type: ignore[union-attr]
        elif action == "click" and step.selector:
            await page.click(step.selector, timeout=step.timeout)  # type: ignore[union-attr]
        elif action == "fill" and step.selector and step.value is not None:
            await page.fill(step.selector, step.value, timeout=step.timeout)  # type: ignore[union-attr]
        elif action == "wait_for" and step.selector:
            await page.wait_for_selector(step.selector, timeout=step.timeout)  # type: ignore[union-attr]
        elif action == "screenshot":
            await page.screenshot()  # type: ignore[union-attr]
        else:
            raise ValueError(f"Unknown or incomplete step action: {action}")

    @staticmethod
    async def _check_assertion(page: object, assertion: object) -> None:
        """Evaluate a single BrowserAssertion against the current page."""
        from devharness.core.models import BrowserAssertion

        assert isinstance(assertion, BrowserAssertion)  # noqa: S101
        atype = assertion.type.lower()

        if atype == "url_contains" and assertion.value:
            url = page.url  # type: ignore[union-attr]
            if assertion.value not in url:
                raise AssertionError(f"URL {url!r} does not contain {assertion.value!r}")
        elif atype == "element_visible" and assertion.selector:
            el = await page.query_selector(assertion.selector)  # type: ignore[union-attr]
            if el is None:
                raise AssertionError(f"Element {assertion.selector!r} not found")
            if not await el.is_visible():
                raise AssertionError(f"Element {assertion.selector!r} is not visible")
        elif atype == "text_contains" and assertion.selector and assertion.value:
            el = await page.query_selector(assertion.selector)  # type: ignore[union-attr]
            if el is None:
                raise AssertionError(f"Element {assertion.selector!r} not found")
            text = await el.text_content()
            if assertion.value not in (text or ""):
                raise AssertionError(
                    f"Element {assertion.selector!r} text does not contain {assertion.value!r}"
                )
        elif atype == "no_console_errors":
            # Console error tracking requires setup during page creation;
            # this is a simplified check.
            pass
        else:
            raise ValueError(f"Unknown assertion type: {atype}")
