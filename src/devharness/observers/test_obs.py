"""Test observer -- runs test suite and parses results.

Parses pytest output into structured TestSummary with specific failure
details including assertion messages and stack traces.
"""

from __future__ import annotations

import json
import logging
import re

import anyio

from devharness.core.models import (
    Observation,
    ObservationSeverity,
    TestFailure,
    TestSummary,
    Thread,
    Turn,
)
from devharness.observers.base import BaseObserver

logger = logging.getLogger(__name__)


class TestObserver(BaseObserver):
    """Run tests and parse results into structured observations."""

    name = "test"

    def __init__(
        self,
        test_command: str = "pytest --tb=short -q",
        run_after_changes: bool = True,
        coverage: bool = False,
    ) -> None:
        self._test_command = test_command
        self._run_after_changes = run_after_changes
        self._coverage = coverage
        self._running = False

    async def observe(self, thread: Thread, turn: Turn | None = None) -> list[Observation]:
        """Run the test suite and parse results."""
        observations: list[Observation] = []
        workspace = thread.config.workspace_root

        try:
            result = await anyio.run_process(
                ["bash", "-c", self._test_command],
                cwd=workspace,
                check=False,
            )
            stdout = result.stdout.decode(errors="replace")[:50_000]
            stderr = result.stderr.decode(errors="replace")[:10_000]

            summary = self._parse_pytest_output(stdout, stderr, result.returncode)

            obs_data = {"test_summary": summary.model_dump(mode="json")}

            if summary.failed > 0 or summary.errored > 0:
                observations.append(
                    Observation(
                        observer_name=self.name,
                        thread_id=thread.id,
                        turn_id=turn.id if turn else None,
                        severity=ObservationSeverity.ERROR,
                        title=f"Tests: {summary.passed} passed, {summary.failed} failed",
                        details=self._format_failures(summary),
                        data=obs_data,
                    )
                )
            else:
                # Success is silent -- but we still record the summary data
                observations.append(
                    Observation(
                        observer_name=self.name,
                        thread_id=thread.id,
                        turn_id=turn.id if turn else None,
                        severity=ObservationSeverity.INFO,
                        title=f"Tests: {summary.total} passed",
                        details="",
                        data=obs_data,
                    )
                )

        except Exception as e:
            observations.append(
                Observation(
                    observer_name=self.name,
                    thread_id=thread.id,
                    turn_id=turn.id if turn else None,
                    severity=ObservationSeverity.ERROR,
                    title="Test runner failed to execute",
                    details=str(e),
                )
            )

        return observations

    def _parse_pytest_output(
        self, stdout: str, stderr: str, returncode: int
    ) -> TestSummary:
        """Parse pytest output into a TestSummary."""
        failures: list[TestFailure] = []
        total = passed = failed = errored = skipped = 0

        # Parse the summary line (e.g., "5 passed, 2 failed in 1.23s")
        summary_match = re.search(
            r"(\d+) passed(?:.*?(\d+) failed)?(?:.*?(\d+) error)?(?:.*?(\d+) skipped)?",
            stdout,
        )
        if summary_match:
            passed = int(summary_match.group(1) or 0)
            failed = int(summary_match.group(2) or 0)
            errored = int(summary_match.group(3) or 0)
            skipped = int(summary_match.group(4) or 0)
            total = passed + failed + errored + skipped

        # Parse individual failures
        failure_blocks = re.split(r"(?=FAILED\s)", stdout)
        for block in failure_blocks:
            fail_match = re.match(r"FAILED\s+(\S+)", block)
            if fail_match:
                test_name = fail_match.group(1)
                # Extract file path and assertion
                file_match = re.search(r"(\S+\.py):(\d+)", block)
                assertion_match = re.search(
                    r"(AssertionError|assert\s.+|E\s+.+)", block
                )
                failures.append(
                    TestFailure(
                        test_name=test_name,
                        file_path=file_match.group(1) if file_match else "",
                        line_number=int(file_match.group(2)) if file_match else None,
                        assertion_message=(
                            assertion_match.group(1)[:500] if assertion_match else ""
                        ),
                        stack_trace=block[:2000],
                    )
                )

        # If no summary found but returncode non-zero, infer failure
        if total == 0 and returncode != 0:
            failed = 1
            total = 1

        return TestSummary(
            total=total,
            passed=passed,
            failed=failed,
            errored=errored,
            skipped=skipped,
            failures=failures,
        )

    def _format_failures(self, summary: TestSummary) -> str:
        """Format failures for agent context injection."""
        lines = []
        for f in summary.failures[:5]:
            lines.append(f"FAILED: {f.test_name}")
            if f.assertion_message:
                lines.append(f"  {f.assertion_message}")
            if f.file_path:
                lines.append(f"  at {f.file_path}:{f.line_number or '?'}")
        return "\n".join(lines)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running
