"""Browser observer -- runs Playwright interaction flows and captures results.

This is the frontend testing observer. It launches a headless browser, executes
click flows defined in YAML, captures screenshots, and reports console errors.
"""

from __future__ import annotations

import logging

from devharness.core.models import (
    BrowserTestResult,
    Observation,
    ObservationSeverity,
    Thread,
    Turn,
)
from devharness.observers.base import BaseObserver

logger = logging.getLogger(__name__)


class BrowserObserver(BaseObserver):
    """Run Playwright browser tests and report results as observations."""

    name = "browser"

    def __init__(self, flow_paths: list[str] | None = None) -> None:
        self._flow_paths = flow_paths or []
        self._running = False

    async def observe(self, thread: Thread, turn: Turn | None = None) -> list[Observation]:
        """Run browser test flows and report results.

        Delegates to the browser_testing module for actual Playwright execution.
        """
        observations: list[Observation] = []

        if not self._flow_paths:
            return observations

        try:
            from devharness.browser_testing.runner import BrowserTestRunner

            runner = BrowserTestRunner(workspace_root=thread.config.workspace_root)
            for flow_path in self._flow_paths:
                result = await runner.run_flow_from_file(flow_path)
                observations.extend(
                    self._result_to_observations(result, thread.id, turn)
                )
        except ImportError:
            logger.warning("Playwright not installed -- skipping browser observer")
        except Exception as e:
            observations.append(
                Observation(
                    observer_name=self.name,
                    thread_id=thread.id,
                    turn_id=turn.id if turn else None,
                    severity=ObservationSeverity.ERROR,
                    title="Browser test runner failed",
                    details=str(e),
                )
            )

        return observations

    def _result_to_observations(
        self, result: BrowserTestResult, thread_id: str, turn: Turn | None
    ) -> list[Observation]:
        """Convert a BrowserTestResult to observations."""
        observations: list[Observation] = []

        if result.passed:
            observations.append(
                Observation(
                    observer_name=self.name,
                    thread_id=thread_id,
                    turn_id=turn.id if turn else None,
                    severity=ObservationSeverity.INFO,
                    title=f"Browser test passed: {result.flow_name}",
                    data={"flow": result.flow_name, "duration_ms": result.duration_ms},
                )
            )
        else:
            details_lines = [
                f"Step {result.failure_step}/{result.steps_total}: {result.failure_reason}",
            ]
            if result.console_errors:
                details_lines.append("Console errors:")
                for err in result.console_errors[:5]:
                    details_lines.append(f"  - {err[:200]}")
            if result.dom_snapshot:
                details_lines.append(f"DOM snapshot: {result.dom_snapshot[:500]}")

            observations.append(
                Observation(
                    observer_name=self.name,
                    thread_id=thread_id,
                    turn_id=turn.id if turn else None,
                    severity=ObservationSeverity.ERROR,
                    title=f"Browser test failed: {result.flow_name}",
                    details="\n".join(details_lines),
                    data={
                        "flow": result.flow_name,
                        "failure_step": result.failure_step,
                        "failure_reason": result.failure_reason,
                        "console_errors": result.console_errors,
                        "screenshots": result.screenshots,
                    },
                )
            )

        return observations

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running
