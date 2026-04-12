"""Verifier that runs the project's test suite via pytest."""

from __future__ import annotations

import logging

import anyio

from devharness.core.models import Thread, Turn, VerificationResult
from devharness.verification.base import BaseVerifier

logger = logging.getLogger(__name__)


class TestVerifier(BaseVerifier):
    """Runs ``pytest`` in the workspace and reports pass/fail."""

    @property
    def name(self) -> str:
        return "test_verifier"

    async def verify(self, thread: Thread, turn: Turn) -> VerificationResult:
        workspace = thread.config.workspace_root
        try:
            result = await anyio.run_process(
                ["python", "-m", "pytest", "--tb=short", "-q"],
                cwd=workspace,
                check=False,
            )
        except FileNotFoundError:
            return VerificationResult(
                verifier_name=self.name,
                passed=False,
                message="pytest not found on PATH",
            )

        stdout = result.stdout.decode(errors="replace")
        stderr = result.stderr.decode(errors="replace")
        passed = result.returncode == 0

        return VerificationResult(
            verifier_name=self.name,
            passed=passed,
            message=stdout if passed else f"{stdout}\n{stderr}".strip(),
            details={
                "returncode": result.returncode,
                "stdout": stdout[-4000:],
                "stderr": stderr[-2000:],
            },
        )
