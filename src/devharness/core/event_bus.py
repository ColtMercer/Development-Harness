"""In-process async pub/sub event bus.

The event bus is the harness's nervous system. Every significant action
emits an Event. Subscribers filter by EventKind (or None for all events).

Subscribers run concurrently via anyio task groups. A failing subscriber
logs the error but does not block other subscribers or the emitter.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

import anyio

from devharness.core.models import Event, EventKind

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    EventHandler = Callable[[Event], Awaitable[None]]

logger = logging.getLogger(__name__)


class EventBus:
    """In-process async pub/sub. Subscribers filter by EventKind."""

    def __init__(self) -> None:
        # None key = wildcard (receives all events)
        self._handlers: dict[EventKind | None, list[EventHandler]] = defaultdict(list)
        self._event_log: list[Event] = []

    def subscribe(self, kind: EventKind | None, handler: EventHandler) -> None:
        """Subscribe to a specific event kind, or None for all events."""
        self._handlers[kind].append(handler)

    def unsubscribe(self, kind: EventKind | None, handler: EventHandler) -> None:
        """Remove a handler. No-op if not found."""
        handlers = self._handlers.get(kind, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: Event) -> None:
        """Emit an event to all matching handlers.

        Handlers for the specific kind + wildcard handlers are all called.
        Each handler runs in its own task so one failure doesn't block others.
        """
        self._event_log.append(event)

        handlers: list[EventHandler] = []
        handlers.extend(self._handlers.get(event.kind, []))
        handlers.extend(self._handlers.get(None, []))

        if not handlers:
            return

        async with anyio.create_task_group() as tg:
            for handler in handlers:
                tg.start_soon(self._safe_call, handler, event)

    @staticmethod
    async def _safe_call(handler: EventHandler, event: Event) -> None:
        """Call a handler, catching and logging any exceptions."""
        try:
            await handler(event)
        except Exception:
            logger.exception(
                "Event handler %s failed for event %s",
                getattr(handler, "__name__", repr(handler)),
                event.kind,
            )

    def events_for_thread(self, thread_id: str) -> list[Event]:
        """Return all events for a given thread, ordered by timestamp."""
        return sorted(
            (e for e in self._event_log if e.thread_id == thread_id),
            key=lambda e: e.timestamp,
        )

    def clear(self) -> None:
        """Clear event log and all handlers. Used in tests."""
        self._event_log.clear()
        self._handlers.clear()
