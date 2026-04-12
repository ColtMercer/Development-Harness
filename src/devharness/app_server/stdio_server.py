"""Stdio JSON-RPC server.

Reads JSON-RPC requests from stdin (one per line), dispatches to handlers,
writes responses to stdout. Events are emitted as JSON-RPC notifications.
"""

from __future__ import annotations

import json
import logging
import sys

import anyio

from devharness.app_server.jsonrpc import JsonRpcDispatcher, JsonRpcNotification, JsonRpcRequest
from devharness.core.event_bus import EventBus
from devharness.core.models import Event

logger = logging.getLogger(__name__)


class StdioServer:
    """JSON-RPC over stdin/stdout."""

    def __init__(self, dispatcher: JsonRpcDispatcher, event_bus: EventBus) -> None:
        self._dispatcher = dispatcher
        self._event_bus = event_bus
        self._send_lock = anyio.Lock()

    async def run(self) -> None:
        """Main loop: read from stdin, dispatch, write to stdout."""
        # Subscribe to event bus to emit notifications
        self._event_bus.subscribe(None, self._on_event)

        async with anyio.create_task_group() as tg:
            tg.start_soon(self._read_loop)

    async def _read_loop(self) -> None:
        """Read JSON-RPC requests from stdin."""
        reader = anyio.wrap_file(sys.stdin)
        async for line in reader:
            line = line.strip()
            if not line:
                continue

            try:
                request = JsonRpcRequest.model_validate_json(line)
                response = await self._dispatcher.dispatch(request)
                await self._write_line(response.model_dump_json())
            except Exception as e:
                logger.exception("Failed to process request")
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {e}"},
                }
                await self._write_line(json.dumps(error_response))

    async def _on_event(self, event: Event) -> None:
        """Emit events as JSON-RPC notifications."""
        notification = JsonRpcNotification(
            method="event",
            params=event.model_dump(mode="json"),
        )
        await self._write_line(notification.model_dump_json())

    async def _write_line(self, data: str) -> None:
        """Thread-safe write to stdout."""
        async with self._send_lock:
            sys.stdout.write(data + "\n")
            sys.stdout.flush()
