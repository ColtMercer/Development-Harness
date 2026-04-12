"""Verifier that runs ruff linting on the workspace."""

from __future__ import annotations

import logging

import anyio

from devharness.core.models import Thread, Turn, VerificationResult
from devharness.verification.base import BaseVerifier

logger = logging.getLogger(__name__)


class LintVerifier(BaseVerifier):
    """Runs ``ruff check`` in the workspace and reports violations."""

    @property
    def name(self) -> str:
        return "lint_verifier"

    async def verify(self, thread: Thread, turn: Turn) -> VerificationResult:
        workspace = thread.config.workspace_root
        try:
            result = await anyio.run_process(
                ["ruff", "check", "."],
                cwd=workspace,
                check=False,
            )
        except FileNotFoundError:
            return VerificationResult(
                verifier_name=self.name,
                passed=False,
                message="ruff not found on PATH",
            )

        stdout = result.stdout.decode(errors="replace")
        stderr = result.stderr.decode(errors="replace")
        passed = result.returncode == 0

        return VerificationResult(
            verifier_name=self.name,
            passed=passed,
            message="No lint violations" if passed else stdout.strip(),
            details={
                "returncode": result.returncode,
                "stdout": stdout[-4000:],
                "stderr": stderr[-2000:],
            },
        )
