"""Observer pipeline orchestrator.

Runs all registered observers concurrently and collects their observations.
"""

from __future__ import annotations

import logging
from typing import Any

import anyio

from devharness.core.event_bus import EventBus
from devharness.core.models import (
    Event,
    EventKind,
    Observation,
    Thread,
    Turn,
)
from devharness.observers.base import BaseObserver

logger = logging.getLogger(__name__)


class ObserverPipeline:
    """Runs observers concurrently and collects observations."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._observers: list[BaseObserver] = []
        self._event_bus = event_bus

    def add_observer(self, observer: BaseObserver) -> None:
        self._observers.append(observer)

    def remove_observer(self, name: str) -> None:
        self._observers = [o for o in self._observers if o.name != name]

    async def observe_all(
        self, thread: Thread, turn: Turn | None = None
    ) -> list[Observation]:
        """Run all observers concurrently and return combined observations."""
        all_observations: list[Observation] = []

        async def run_observer(observer: BaseObserver) -> None:
            try:
                observations = await observer.observe(thread, turn)
                all_observations.extend(observations)
            except Exception:
                logger.exception("Observer %s failed", observer.name)

        async with anyio.create_task_group() as tg:
            for observer in self._observers:
                tg.start_soon(run_observer, observer)

        # Emit observation events
        if self._event_bus:
            for obs in all_observations:
                await self._event_bus.emit(
                    Event(
                        thread_id=thread.id,
                        turn_id=turn.id if turn else None,
                        kind=EventKind.OBSERVATION,
                        data=obs.model_dump(mode="json"),
                    )
                )

        return all_observations

    async def start_all(self) -> None:
        """Start continuous monitoring on all observers."""
        for observer in self._observers:
            try:
                await observer.start()
            except Exception:
                logger.exception("Failed to start observer %s", observer.name)

    async def stop_all(self) -> None:
        """Stop all continuous monitoring."""
        for observer in self._observers:
            try:
                await observer.stop()
            except Exception:
                logger.exception("Failed to stop observer %s", observer.name)

    def list_observers(self) -> list[str]:
        return [o.name for o in self._observers]
