"""Enforcement engine -- runs architectural checks with agent-readable errors.

When a rule is violated, the correction_prompt is injected into the agent's
context, giving it specific instructions on how to fix the violation.
"""

from __future__ import annotations

import logging

import anyio

from devharness.core.models import EnforcementResult, EnforcementRule

logger = logging.getLogger(__name__)


class EnforcementEngine:
    """Run mechanical enforcement rules and collect results."""

    def __init__(self) -> None:
        self._rules: list[EnforcementRule] = []

    def add_rule(self, rule: EnforcementRule) -> None:
        self._rules.append(rule)

    def remove_rule(self, name: str) -> None:
        self._rules = [r for r in self._rules if r.name != name]

    async def run_all(self, workspace_root: str) -> list[EnforcementResult]:
        """Run all enabled enforcement rules."""
        results: list[EnforcementResult] = []
        for rule in self._rules:
            if not rule.enabled:
                continue
            result = await self._run_rule(rule, workspace_root)
            results.append(result)
        return results

    async def _run_rule(
        self, rule: EnforcementRule, workspace_root: str
    ) -> EnforcementResult:
        """Run a single enforcement rule."""
        import time
        import re

        start = time.monotonic()
        try:
            proc = await anyio.run_process(
                ["bash", "-c", rule.check_command],
                cwd=workspace_root,
                check=False,
            )
            stdout = proc.stdout.decode(errors="replace")
            stderr = proc.stderr.decode(errors="replace")
            output = stdout + stderr

            violations: list[str] = []
            if proc.returncode != 0:
                if rule.error_pattern:
                    for match in re.finditer(rule.error_pattern, output):
                        violations.append(match.group(0)[:500])
                else:
                    # Each non-empty line is a violation
                    violations = [
                        l.strip()[:500]
                        for l in output.split("\n")
                        if l.strip()
                    ][:20]

            duration_ms = (time.monotonic() - start) * 1000
            return EnforcementResult(
                rule_name=rule.name,
                passed=proc.returncode == 0,
                violations=violations,
                correction_prompt=rule.correction_prompt if violations else None,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            return EnforcementResult(
                rule_name=rule.name,
                passed=False,
                violations=[f"Rule execution error: {e}"],
                duration_ms=duration_ms,
            )

    def list_rules(self) -> list[EnforcementRule]:
        return list(self._rules)
