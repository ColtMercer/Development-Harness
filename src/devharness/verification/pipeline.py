"""Verification pipeline -- runs verifiers concurrently after each turn."""

from __future__ import annotations

import logging
import time

import anyio

from devharness.core.models import Thread, Turn, VerificationReport, VerificationResult
from devharness.verification.base import BaseVerifier

logger = logging.getLogger(__name__)


class VerificationPipeline:
    """Executes a set of verifiers concurrently and aggregates results.

    Usage::

        pipeline = VerificationPipeline()
        pipeline.add_verifier(TestVerifier())
        pipeline.add_verifier(LintVerifier())
        report = await pipeline.run(thread, turn)
    """

    def __init__(self) -> None:
        self._verifiers: list[BaseVerifier] = []

    def add_verifier(self, verifier: BaseVerifier) -> None:
        """Append a verifier to the pipeline."""
        self._verifiers.append(verifier)

    async def run(self, thread: Thread, turn: Turn) -> VerificationReport:
        """Run all verifiers concurrently and return an aggregate report.

        Each verifier runs in its own task within an ``anyio.create_task_group``.
        A failing verifier does not cancel the others; its exception is
        captured as a failed :class:`VerificationResult`.
        """
        results: list[VerificationResult] = []

        async def _run_one(verifier: BaseVerifier) -> None:
            t0 = time.monotonic()
            try:
                result = await verifier.verify(thread, turn)
                result.duration_ms = (time.monotonic() - t0) * 1000
                results.append(result)
            except Exception as exc:
                elapsed = (time.monotonic() - t0) * 1000
                logger.exception("Verifier %s raised an exception", verifier.name)
                results.append(
                    VerificationResult(
                        verifier_name=verifier.name,
                        passed=False,
                        message=f"Verifier raised {type(exc).__name__}: {exc}",
                        duration_ms=elapsed,
                    )
                )

        async with anyio.create_task_group() as tg:
            for v in self._verifiers:
                tg.start_soon(_run_one, v)

        return VerificationReport(
            thread_id=thread.id,
            turn_id=turn.id,
            results=results,
            all_passed=all(r.passed for r in results),
        )
