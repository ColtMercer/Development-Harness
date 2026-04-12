"""Tests for devharness.core.event_bus.EventBus."""

from __future__ import annotations

import pytest

from devharness.core.event_bus import EventBus
from devharness.core.models import Event, EventKind


# ---------------------------------------------------------------------------
# Emit and subscribe
# ---------------------------------------------------------------------------


async def test_emit_calls_subscriber(event_bus: EventBus) -> None:
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    event_bus.subscribe(EventKind.THREAD_CREATED, handler)

    event = Event(thread_id="t1", kind=EventKind.THREAD_CREATED)
    await event_bus.emit(event)

    assert len(received) == 1
    assert received[0].id == event.id


async def test_emit_only_matching_kind(event_bus: EventBus) -> None:
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    event_bus.subscribe(EventKind.THREAD_CREATED, handler)

    # Emit a different kind -- handler should not be called
    event = Event(thread_id="t1", kind=EventKind.TURN_START)
    await event_bus.emit(event)

    assert len(received) == 0


async def test_multiple_subscribers(event_bus: EventBus) -> None:
    results_a: list[str] = []
    results_b: list[str] = []

    async def handler_a(event: Event) -> None:
        results_a.append(event.id)

    async def handler_b(event: Event) -> None:
        results_b.append(event.id)

    event_bus.subscribe(EventKind.TURN_END, handler_a)
    event_bus.subscribe(EventKind.TURN_END, handler_b)

    event = Event(thread_id="t1", kind=EventKind.TURN_END)
    await event_bus.emit(event)

    assert len(results_a) == 1
    assert len(results_b) == 1


# ---------------------------------------------------------------------------
# Wildcard subscription
# ---------------------------------------------------------------------------


async def test_wildcard_subscription(event_bus: EventBus) -> None:
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    event_bus.subscribe(None, handler)

    await event_bus.emit(Event(thread_id="t1", kind=EventKind.THREAD_CREATED))
    await event_bus.emit(Event(thread_id="t1", kind=EventKind.TURN_START))
    await event_bus.emit(Event(thread_id="t1", kind=EventKind.AGENT_STARTED))

    assert len(received) == 3


async def test_wildcard_and_specific(event_bus: EventBus) -> None:
    wildcard_events: list[Event] = []
    specific_events: list[Event] = []

    async def wildcard_handler(event: Event) -> None:
        wildcard_events.append(event)

    async def specific_handler(event: Event) -> None:
        specific_events.append(event)

    event_bus.subscribe(None, wildcard_handler)
    event_bus.subscribe(EventKind.TURN_START, specific_handler)

    event = Event(thread_id="t1", kind=EventKind.TURN_START)
    await event_bus.emit(event)

    # Both handlers should fire
    assert len(wildcard_events) == 1
    assert len(specific_events) == 1


# ---------------------------------------------------------------------------
# Handler errors don't propagate
# ---------------------------------------------------------------------------


async def test_handler_error_does_not_propagate(event_bus: EventBus) -> None:
    good_results: list[str] = []

    async def bad_handler(event: Event) -> None:
        raise RuntimeError("boom")

    async def good_handler(event: Event) -> None:
        good_results.append(event.id)

    event_bus.subscribe(EventKind.ERROR, bad_handler)
    event_bus.subscribe(EventKind.ERROR, good_handler)

    event = Event(thread_id="t1", kind=EventKind.ERROR)
    # Should not raise even though bad_handler throws
    await event_bus.emit(event)

    assert len(good_results) == 1


# ---------------------------------------------------------------------------
# events_for_thread filtering
# ---------------------------------------------------------------------------


async def test_events_for_thread(event_bus: EventBus) -> None:
    await event_bus.emit(Event(thread_id="t1", kind=EventKind.THREAD_CREATED))
    await event_bus.emit(Event(thread_id="t2", kind=EventKind.THREAD_CREATED))
    await event_bus.emit(Event(thread_id="t1", kind=EventKind.TURN_START))

    t1_events = event_bus.events_for_thread("t1")
    assert len(t1_events) == 2
    assert all(e.thread_id == "t1" for e in t1_events)

    t2_events = event_bus.events_for_thread("t2")
    assert len(t2_events) == 1


async def test_events_for_thread_ordering(event_bus: EventBus) -> None:
    e1 = Event(thread_id="t1", kind=EventKind.THREAD_CREATED)
    e2 = Event(thread_id="t1", kind=EventKind.TURN_START)
    e3 = Event(thread_id="t1", kind=EventKind.TURN_END)

    await event_bus.emit(e1)
    await event_bus.emit(e2)
    await event_bus.emit(e3)

    events = event_bus.events_for_thread("t1")
    assert len(events) == 3
    # Should be sorted by timestamp (all created in order)
    assert events[0].kind == EventKind.THREAD_CREATED
    assert events[1].kind == EventKind.TURN_START
    assert events[2].kind == EventKind.TURN_END


async def test_events_for_nonexistent_thread(event_bus: EventBus) -> None:
    events = event_bus.events_for_thread("nonexistent")
    assert events == []


# ---------------------------------------------------------------------------
# Unsubscribe
# ---------------------------------------------------------------------------


async def test_unsubscribe(event_bus: EventBus) -> None:
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    event_bus.subscribe(EventKind.TURN_START, handler)
    event_bus.unsubscribe(EventKind.TURN_START, handler)

    await event_bus.emit(Event(thread_id="t1", kind=EventKind.TURN_START))
    assert len(received) == 0


async def test_unsubscribe_nonexistent_is_noop(event_bus: EventBus) -> None:
    async def handler(event: Event) -> None:
        pass

    # Should not raise
    event_bus.unsubscribe(EventKind.TURN_START, handler)


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


async def test_clear(event_bus: EventBus) -> None:
    async def handler(event: Event) -> None:
        pass

    event_bus.subscribe(EventKind.TURN_START, handler)
    await event_bus.emit(Event(thread_id="t1", kind=EventKind.TURN_START))

    event_bus.clear()

    assert event_bus.events_for_thread("t1") == []
