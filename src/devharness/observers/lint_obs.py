"""Lint observer -- runs linter and reports new issues.

Diffs against baseline to report only issues introduced by recent changes.
"""

from __future__ import annotations

import json
import logging

import anyio

from devharness.core.models import Observation, ObservationSeverity, Thread, Turn
from devharness.observers.base import BaseObserver

logger = logging.getLogger(__name__)


class LintObserver(BaseObserver):
    """Run linter after changes and report new issues."""

    name = "lint"

    def __init__(
        self,
        lint_command: str = "ruff check --output-format json",
        run_after_changes: bool = True,
    ) -> None:
        self._lint_command = lint_command
        self._run_after_changes = run_after_changes
        self._baseline_count: int | None = None
        self._running = False

    async def observe(self, thread: Thread, turn: Turn | None = None) -> list[Observation]:
        """Run linter and report issues."""
        observations: list[Observation] = []
        workspace = thread.config.workspace_root

        try:
            result = await anyio.run_process(
                ["bash", "-c", self._lint_command],
                cwd=workspace,
                check=False,
            )
            stdout = result.stdout.decode(errors="replace")[:50_000]

            # Try to parse JSON output (ruff --output-format json)
            issues = self._parse_lint_output(stdout)
            current_count = len(issues)

            # Report new issues relative to baseline
            new_issues = current_count
            if self._baseline_count is not None:
                new_issues = max(0, current_count - self._baseline_count)

            if new_issues > 0:
                issue_details = "\n".join(
                    f"  {i.get('filename', '?')}:{i.get('location', {}).get('row', '?')}: "
                    f"{i.get('code', '?')} {i.get('message', '?')}"
                    for i in issues[:10]
                )
                observations.append(
                    Observation(
                        observer_name=self.name,
                        thread_id=thread.id,
                        turn_id=turn.id if turn else None,
                        severity=ObservationSeverity.WARNING,
                        title=f"{new_issues} new lint issue(s)",
                        details=issue_details,
                        data={
                            "total_issues": current_count,
                            "new_issues": new_issues,
                            "issues": issues[:20],
                        },
                    )
                )

            # Update baseline
            if self._baseline_count is None:
                self._baseline_count = current_count

        except Exception as e:
            logger.warning("Lint observer failed: %s", e)

        return observations

    def _parse_lint_output(self, output: str) -> list[dict]:
        """Parse lint output. Tries JSON first, falls back to line count."""
        try:
            return json.loads(output)
        except (json.JSONDecodeError, ValueError):
            # Fall back to counting non-empty lines
            lines = [l.strip() for l in output.split("\n") if l.strip()]
            return [{"message": l} for l in lines]

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
        self._baseline_count = None

    @property
    def is_running(self) -> bool:
        return self._running
