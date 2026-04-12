"""Metrics observer -- collects simple application metrics."""

from __future__ import annotations

import logging

from devharness.core.models import Observation, ObservationSeverity, Thread, Turn
from devharness.observers.base import BaseObserver

logger = logging.getLogger(__name__)


class MetricsObserver(BaseObserver):
    """Collect simple process and application metrics."""

    name = "metrics"

    def __init__(self, collect_interval_seconds: int = 60) -> None:
        self._interval = collect_interval_seconds
        self._running = False

    async def observe(self, thread: Thread, turn: Turn | None = None) -> list[Observation]:
        """Collect current metrics. Uses psutil if available."""
        observations: list[Observation] = []

        try:
            import psutil

            cpu_pct = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()

            if cpu_pct > 90 or mem.percent > 90:
                observations.append(
                    Observation(
                        observer_name=self.name,
                        thread_id=thread.id,
                        turn_id=turn.id if turn else None,
                        severity=ObservationSeverity.WARNING,
                        title=f"High resource usage: CPU {cpu_pct}%, RAM {mem.percent}%",
                        data={
                            "cpu_percent": cpu_pct,
                            "memory_percent": mem.percent,
                            "memory_available_mb": mem.available // (1024 * 1024),
                        },
                    )
                )
        except ImportError:
            pass  # psutil is optional

        return observations

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running
