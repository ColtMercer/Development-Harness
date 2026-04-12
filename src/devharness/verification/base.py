"""Abstract base class for verifiers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from devharness.core.models import Thread, Turn, VerificationResult


class BaseVerifier(ABC):
    """A verifier runs a single check against the workspace after a turn.

    Concrete verifiers implement :meth:`verify` which receives the current
    :class:`Thread` and :class:`Turn` and returns a :class:`VerificationResult`.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this verifier (used in manifests and reports)."""

    @abstractmethod
    async def verify(self, thread: Thread, turn: Turn) -> VerificationResult:
        """Run the verification check.

        Parameters
        ----------
        thread:
            The current thread (provides workspace root via config).
        turn:
            The turn that just completed.

        Returns
        -------
        VerificationResult
            A result indicating pass/fail with diagnostics.
        """
