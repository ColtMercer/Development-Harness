"""Verifier that checks for the existence of required files."""

from __future__ import annotations

import logging
from pathlib import Path

from devharness.core.models import Thread, Turn, VerificationResult
from devharness.verification.base import BaseVerifier

logger = logging.getLogger(__name__)

# Sensible defaults -- these can be overridden at init time.
_DEFAULT_REQUIRED: list[str] = []


class FileExistenceVerifier(BaseVerifier):
    """Verifies that a configurable set of files exist in the workspace.

    Parameters
    ----------
    required_files:
        List of relative paths (from workspace root) that must exist.
        An empty list means the check always passes.
    """

    def __init__(self, required_files: list[str] | None = None) -> None:
        self._required = required_files if required_files is not None else list(_DEFAULT_REQUIRED)

    @property
    def name(self) -> str:
        return "file_existence_verifier"

    async def verify(self, thread: Thread, turn: Turn) -> VerificationResult:
        if not self._required:
            return VerificationResult(
                verifier_name=self.name,
                passed=True,
                message="No required files configured",
            )

        workspace = Path(thread.config.workspace_root)
        missing: list[str] = []

        for rel in self._required:
            target = workspace / rel
            if not target.exists():
                missing.append(rel)

        if missing:
            return VerificationResult(
                verifier_name=self.name,
                passed=False,
                message=f"{len(missing)} required file(s) missing: {', '.join(missing)}",
                details={"missing": missing, "required": self._required},
            )

        return VerificationResult(
            verifier_name=self.name,
            passed=True,
            message=f"All {len(self._required)} required files exist",
            details={"required": self._required},
        )
