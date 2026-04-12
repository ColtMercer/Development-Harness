"""Simple counters and timers for harness telemetry.

Provides a lightweight :class:`MetricsCollector` that tracks named
counters and wall-clock timers without any external dependencies.
"""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Iterator


class MetricsCollector:
    """In-memory metrics collector with counters and timers.

    Thread-safety note: this implementation is *not* thread-safe; it is
    designed for single-threaded async usage within one event loop.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._timers: dict[str, list[float]] = defaultdict(list)

    def increment(self, name: str, amount: int = 1) -> None:
        """Increment counter *name* by *amount* (default 1)."""
        self._counters[name] += amount

    @contextmanager
    def timer(self, name: str) -> Iterator[None]:
        """Context manager that records elapsed wall-clock time (ms).

        Usage::

            with collector.timer("tool.execute"):
                await run_tool()
        """
        start = time.monotonic()
        try:
            yield
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000
            self._timers[name].append(round(elapsed_ms, 2))

    def get_metrics(self) -> dict[str, Any]:
        """Return a snapshot of all collected metrics.

        Returns a dict with ``"counters"`` and ``"timers"`` keys.
        Each timer entry contains ``count``, ``total_ms``, ``min_ms``,
        ``max_ms``, and ``avg_ms``.
        """
        timer_stats: dict[str, dict[str, float]] = {}
        for name, samples in self._timers.items():
            if not samples:
                continue
            timer_stats[name] = {
                "count": len(samples),
                "total_ms": round(sum(samples), 2),
                "min_ms": round(min(samples), 2),
                "max_ms": round(max(samples), 2),
                "avg_ms": round(sum(samples) / len(samples), 2),
            }

        return {
            "counters": dict(self._counters),
            "timers": timer_stats,
        }

    def reset(self) -> None:
        """Clear all collected metrics."""
        self._counters.clear()
        self._timers.clear()
