"""Slack Socket Mode integration.

This module provides an outbound WebSocket connection to Slack using
Socket Mode (no inbound webhooks required). It subscribes to harness
events and forwards notifications to configured Slack channels.
"""

from __future__ import annotations

import logging
from typing import Any

from devharness.core.event_bus import EventBus
from devharness.core.models import Event, EventKind, SlackConfig

logger = logging.getLogger(__name__)

# Mapping from notify_on config strings to EventKinds.
_NOTIFY_MAP: dict[str, EventKind] = {
    "approval_requested": EventKind.APPROVAL_REQUESTED,
    "turn_complete": EventKind.TURN_END,
    "turn_failed": EventKind.THREAD_FAILED,
    "browser_test_failed": EventKind.BROWSER_TEST_FAILED,
    "verification_failed": EventKind.VERIFICATION_END,
    "thread_completed": EventKind.THREAD_COMPLETED,
    "error": EventKind.ERROR,
}


class SlackIntegration:
    """Socket Mode Slack client for the harness.

    Connects to Slack via an outbound WebSocket (no public URL needed).
    Listens for harness events and posts notifications to configured
    channels. Also handles interactive messages (button clicks for
    approvals).

    Parameters
    ----------
    config:
        Slack configuration (tokens, channels, notification preferences).
    event_bus:
        The shared event bus to subscribe to.
    """

    def __init__(self, config: SlackConfig, event_bus: EventBus) -> None:
        self._config = config
        self._event_bus = event_bus
        self._socket_client: Any = None
        self._web_client: Any = None
        self._running = False

    async def start(self) -> None:
        """Connect to Slack via Socket Mode and subscribe to events.

        Requires the ``slack_sdk`` package. If not installed or if the
        config is disabled, this method returns immediately.
        """
        if not self._config.enabled:
            logger.info("Slack integration is disabled")
            return

        try:
            from slack_sdk.socket_mode.aiohttp import SocketModeClient
            from slack_sdk.web.async_client import AsyncWebClient
        except ImportError:
            logger.warning(
                "slack_sdk is not installed; Slack integration will not start. "
                "Install with: pip install slack_sdk aiohttp"
            )
            return

        self._web_client = AsyncWebClient(token=self._config.bot_token)
        self._socket_client = SocketModeClient(
            app_token=self._config.app_token,
            web_client=self._web_client,
        )

        # Subscribe to harness events for notification forwarding.
        self._subscribe_to_events()

        # Register Socket Mode event handlers.
        self._socket_client.socket_mode_request_listeners.append(
            self._handle_socket_event
        )

        await self._socket_client.connect()
        self._running = True
        logger.info("Slack Socket Mode client connected")

    async def stop(self) -> None:
        """Disconnect from Slack."""
        if self._socket_client and self._running:
            await self._socket_client.disconnect()
            self._running = False
            logger.info("Slack Socket Mode client disconnected")

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Event bus subscriptions
    # ------------------------------------------------------------------

    def _subscribe_to_events(self) -> None:
        """Subscribe to configured event kinds on the harness event bus."""
        subscribed: set[EventKind] = set()
        for notify_key in self._config.notify_on:
            kind = _NOTIFY_MAP.get(notify_key)
            if kind and kind not in subscribed:
                self._event_bus.subscribe(kind, self._on_harness_event)
                subscribed.add(kind)

    async def _on_harness_event(self, event: Event) -> None:
        """Forward a harness event to the appropriate Slack channel."""
        from devharness.integrations.slack.messages import build_notification

        channel = self._config.channel
        if (
            event.kind == EventKind.APPROVAL_REQUESTED
            and self._config.approval_channel
        ):
            channel = self._config.approval_channel

        blocks = build_notification(
            title=f"Harness: {event.kind.value}",
            body=event.data.get("message", str(event.data)),
            thread_id=event.thread_id,
        )

        await self._post_message(channel, blocks)

    async def _post_message(
        self, channel: str, blocks: dict[str, Any]
    ) -> None:
        """Post a Block Kit message to a Slack channel."""
        if not self._web_client:
            logger.warning("Cannot post to Slack: web client not initialised")
            return
        try:
            await self._web_client.chat_postMessage(
                channel=channel,
                blocks=blocks["blocks"],
                text=blocks.get("text", "Harness notification"),
            )
        except Exception:
            logger.exception("Failed to post message to Slack channel %s", channel)

    # ------------------------------------------------------------------
    # Socket Mode event handling
    # ------------------------------------------------------------------

    async def _handle_socket_event(self, client: Any, req: Any) -> None:
        """Handle incoming Socket Mode events (slash commands, interactions)."""
        from devharness.integrations.slack.handlers import handle_socket_request

        await handle_socket_request(client, req, self._event_bus, self._web_client)
