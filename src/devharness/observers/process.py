"""Process observer -- monitors dev servers and background processes.

Watches stdout/stderr for errors, detects crashes, captures exit codes.
"""

from __future__ import annotations

import logging

import anyio

from devharness.core.models import Observation, ObservationSeverity, Thread, Turn
from devharness.observers.base import BaseObserver

logger = logging.getLogger(__name__)


class ProcessObserver(BaseObserver):
    """Monitor spawned processes for errors and crashes."""

    name = "process"

    def __init__(self, watch_commands: list[str] | None = None) -> None:
        self._watch_commands = watch_commands or []
        self._running = False

    async def observe(self, thread: Thread, turn: Turn | None = None) -> list[Observation]:
        """Check tracked processes for issues."""
        observations: list[Observation] = []

        # In a full implementation, this would check tracked process health.
        # For now, return empty list -- processes are tracked via start/stop.

        return observations

    async def start(self) -> None:
        self._running = True
        logger.info("ProcessObserver started, watching: %s", self._watch_commands)

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running
