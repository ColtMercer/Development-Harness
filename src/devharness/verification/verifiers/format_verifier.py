"""Verifier that checks code formatting via ruff format."""

from __future__ import annotations

import logging

import anyio

from devharness.core.models import Thread, Turn, VerificationResult
from devharness.verification.base import BaseVerifier

logger = logging.getLogger(__name__)


class FormatVerifier(BaseVerifier):
    """Runs ``ruff format --check`` and fails if files would be reformatted."""

    @property
    def name(self) -> str:
        return "format_verifier"

    async def verify(self, thread: Thread, turn: Turn) -> VerificationResult:
        workspace = thread.config.workspace_root
        try:
            result = await anyio.run_process(
                ["ruff", "format", "--check", "."],
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
            message="All files formatted correctly" if passed else stdout.strip(),
            details={
                "returncode": result.returncode,
                "stdout": stdout[-4000:],
                "stderr": stderr[-2000:],
            },
        )
