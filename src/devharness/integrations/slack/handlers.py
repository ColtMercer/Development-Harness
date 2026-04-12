"""Slack event and interaction handlers.

Handles slash commands (``/harness run``, ``/harness status``,
``/harness observe``) and interactive button clicks (approve / deny).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from devharness.core.event_bus import EventBus
from devharness.core.models import ApprovalStatus, Event, EventKind

logger = logging.getLogger(__name__)


async def handle_socket_request(
    client: Any,
    req: Any,
    event_bus: EventBus,
    web_client: Any,
) -> None:
    """Top-level dispatcher for Socket Mode requests.

    Parameters
    ----------
    client:
        The ``SocketModeClient`` instance (used to acknowledge the request).
    req:
        The incoming ``SocketModeRequest``.
    event_bus:
        The harness event bus for emitting events from Slack interactions.
    web_client:
        The Slack ``AsyncWebClient`` for posting responses.
    """
    try:
        from slack_sdk.socket_mode.response import SocketModeResponse
    except ImportError:
        logger.warning("slack_sdk not available; cannot handle socket request")
        return

    payload = req.payload or {}
    req_type = req.type

    # Acknowledge the request immediately.
    response = SocketModeResponse(envelope_id=req.envelope_id)
    await client.send_socket_mode_response(response)

    if req_type == "slash_commands":
        await _handle_slash_command(payload, event_bus, web_client)
    elif req_type == "interactive":
        await _handle_interaction(payload, event_bus, web_client)
    else:
        logger.debug("Ignoring Socket Mode request type: %s", req_type)


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------


async def _handle_slash_command(
    payload: dict[str, Any],
    event_bus: EventBus,
    web_client: Any,
) -> None:
    """Handle ``/harness <subcommand>`` slash commands."""
    command = payload.get("command", "")
    text = (payload.get("text") or "").strip()
    channel = payload.get("channel_id", "")
    user = payload.get("user_id", "")

    parts = text.split(maxsplit=1)
    subcommand = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""

    if subcommand == "run":
        await _cmd_run(args, channel, user, event_bus, web_client)
    elif subcommand == "status":
        await _cmd_status(args, channel, user, event_bus, web_client)
    elif subcommand == "observe":
        await _cmd_observe(args, channel, user, event_bus, web_client)
    else:
        await _reply(
            web_client,
            channel,
            f"Unknown subcommand: `{subcommand}`. "
            f"Available: `run`, `status`, `observe`.",
        )


async def _cmd_run(
    args: str,
    channel: str,
    user: str,
    event_bus: EventBus,
    web_client: Any,
) -> None:
    """Handle ``/harness run <task>``."""
    if not args:
        await _reply(web_client, channel, "Usage: `/harness run <task description>`")
        return

    # Emit an event so the orchestrator can pick it up.
    await event_bus.emit(
        Event(
            thread_id="slack",
            kind=EventKind.THREAD_CREATED,
            data={
                "source": "slack",
                "channel": channel,
                "user": user,
                "task": args,
            },
        )
    )
    await _reply(web_client, channel, f"Starting task: _{args}_")


async def _cmd_status(
    args: str,
    channel: str,
    user: str,
    event_bus: EventBus,
    web_client: Any,
) -> None:
    """Handle ``/harness status [thread_id]``."""
    thread_id = args.strip() if args else None

    if thread_id:
        events = event_bus.events_for_thread(thread_id)
        if not events:
            await _reply(web_client, channel, f"No events found for thread `{thread_id}`")
        else:
            last = events[-1]
            await _reply(
                web_client,
                channel,
                f"Thread `{thread_id}` -- last event: *{last.kind.value}* at {last.timestamp.isoformat()}",
            )
    else:
        await _reply(
            web_client,
            channel,
            "Usage: `/harness status <thread_id>`\nOmit thread_id for a summary of all active threads.",
        )


async def _cmd_observe(
    args: str,
    channel: str,
    user: str,
    event_bus: EventBus,
    web_client: Any,
) -> None:
    """Handle ``/harness observe [thread_id]``."""
    thread_id = args.strip() if args else None

    if not thread_id:
        await _reply(web_client, channel, "Usage: `/harness observe <thread_id>`")
        return

    # Subscribe this channel to all events for the given thread.
    async def _forward(event: Event) -> None:
        if event.thread_id == thread_id:
            await _reply(
                web_client,
                channel,
                f"`[{event.kind.value}]` {event.data.get('message', json.dumps(event.data, default=str)[:200])}",
            )

    event_bus.subscribe(None, _forward)
    await _reply(
        web_client,
        channel,
        f"Now observing thread `{thread_id}`. Events will be posted to this channel.",
    )


# ---------------------------------------------------------------------------
# Interactive messages (button clicks)
# ---------------------------------------------------------------------------


async def _handle_interaction(
    payload: dict[str, Any],
    event_bus: EventBus,
    web_client: Any,
) -> None:
    """Handle interactive message payloads (approve/deny buttons)."""
    actions = payload.get("actions", [])
    user = payload.get("user", {})
    user_id = user.get("id", "unknown")
    channel = payload.get("channel", {}).get("id", "")

    for action in actions:
        action_id = action.get("action_id", "")
        approval_id = action.get("value", "")

        if action_id == "approve":
            await event_bus.emit(
                Event(
                    thread_id="slack",
                    kind=EventKind.APPROVAL_RESOLVED,
                    data={
                        "approval_id": approval_id,
                        "status": ApprovalStatus.USER_APPROVED.value,
                        "decided_by": f"slack:{user_id}",
                    },
                )
            )
            await _reply(web_client, channel, f"Approved by <@{user_id}>")

        elif action_id == "deny":
            await event_bus.emit(
                Event(
                    thread_id="slack",
                    kind=EventKind.APPROVAL_RESOLVED,
                    data={
                        "approval_id": approval_id,
                        "status": ApprovalStatus.DENIED.value,
                        "decided_by": f"slack:{user_id}",
                    },
                )
            )
            await _reply(web_client, channel, f"Denied by <@{user_id}>")

        else:
            logger.debug("Unknown interactive action: %s", action_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _reply(web_client: Any, channel: str, text: str) -> None:
    """Post a simple text message to a Slack channel."""
    if not web_client:
        logger.warning("Cannot reply: Slack web client not available")
        return
    try:
        await web_client.chat_postMessage(channel=channel, text=text)
    except Exception:
        logger.exception("Failed to post reply to Slack channel %s", channel)
