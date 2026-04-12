"""Tool call timing spans.

Provides an async context manager that emits TOOL_CALL_START and
TOOL_CALL_END events on the event bus, capturing elapsed wall-clock
time.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

from devharness.core.models import Event, EventKind

if TYPE_CHECKING:
    from devharness.core.event_bus import EventBus
    from devharness.core.models import ToolCall


@asynccontextmanager
async def tool_span(
    event_bus: EventBus,
    thread_id: str,
    turn_id: str,
    tool_call: ToolCall,
) -> AsyncIterator[None]:
    """Async context manager that brackets a tool call with timing events.

    Usage::

        async with tool_span(bus, thread_id, turn_id, tc):
            result = await execute_tool(tc)

    Emits :attr:`EventKind.TOOL_CALL_START` on entry and
    :attr:`EventKind.TOOL_CALL_END` on exit with ``duration_ms`` in
    the event data.
    """
    start_event = Event(
        thread_id=thread_id,
        turn_id=turn_id,
        kind=EventKind.TOOL_CALL_START,
        data={
            "tool_call_id": tool_call.id,
            "tool_name": tool_call.tool_name,
            "arguments": tool_call.arguments,
        },
    )
    await event_bus.emit(start_event)

    start_time = time.monotonic()
    error: str | None = None
    try:
        yield
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        end_data: dict[str, Any] = {
            "tool_call_id": tool_call.id,
            "tool_name": tool_call.tool_name,
            "duration_ms": round(elapsed_ms, 2),
        }
        if error is not None:
            end_data["error"] = error

        end_event = Event(
            thread_id=thread_id,
            turn_id=turn_id,
            kind=EventKind.TOOL_CALL_END,
            data=end_data,
        )
        await event_bus.emit(end_event)
