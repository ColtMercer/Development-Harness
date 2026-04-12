"""Parse streaming JSON output from agent subprocesses into AgentEvent objects.

Each parser handles a single line of JSON from the respective CLI and
returns an ``AgentEvent`` or ``None`` (for lines that should be ignored).
Malformed JSON is caught and returned as an error event so the harness
never crashes on bad output.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from devharness.core.models import AgentEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Claude Code parser
# ---------------------------------------------------------------------------


def parse_claude_code_event(line: str) -> AgentEvent | None:
    """Parse a single line of Claude Code ``--output-format stream-json``.

    Claude Code emits newline-delimited JSON objects with a ``type`` field.
    Known types include:

    * ``assistant`` -- text output (delta in ``content``)
    * ``tool_use`` -- agent is calling a tool
    * ``tool_result`` -- result returned to the agent
    * ``result`` -- final aggregated result
    * ``error`` -- CLI-level error
    * ``system`` -- system/status messages (often ignored)

    Returns ``None`` for blank lines or system bookkeeping we don't surface.
    """
    stripped = line.strip()
    if not stripped:
        return None

    try:
        payload: dict[str, Any] = json.loads(stripped)
    except json.JSONDecodeError as exc:
        logger.debug("Claude Code: ignoring non-JSON line: %s", stripped[:120])
        return AgentEvent(
            type="error",
            data={"message": f"JSON parse error: {exc}", "raw_line": stripped[:500]},
        )

    event_type = payload.get("type", "")

    if event_type in ("assistant", "text"):
        return AgentEvent(
            type="text",
            data={
                "content": payload.get("content", ""),
                "subtype": payload.get("subtype", ""),
            },
        )

    if event_type == "tool_use":
        return AgentEvent(
            type="tool_call",
            data={
                "tool_name": payload.get("tool", payload.get("name", "")),
                "tool_call_id": payload.get("id", ""),
                "arguments": payload.get("input", payload.get("arguments", {})),
            },
        )

    if event_type == "tool_result":
        return AgentEvent(
            type="tool_result",
            data={
                "tool_call_id": payload.get("tool_use_id", payload.get("id", "")),
                "output": payload.get("content", payload.get("output", "")),
                "is_error": payload.get("is_error", False),
            },
        )

    if event_type == "result":
        return AgentEvent(
            type="done",
            data={
                "content": payload.get("result", payload.get("content", "")),
                "cost": payload.get("cost_usd", payload.get("cost", None)),
                "duration_ms": payload.get("duration_ms", None),
                "token_usage": payload.get("usage", {}),
            },
        )

    if event_type == "error":
        return AgentEvent(
            type="error",
            data={
                "message": payload.get("error", payload.get("message", str(payload))),
            },
        )

    # system / ping / progress -- silently skip
    if event_type in ("system", "ping", "progress", "start"):
        return None

    # Unknown type -- pass through as raw data so nothing is lost.
    logger.debug("Claude Code: unrecognised event type %r", event_type)
    return AgentEvent(type="text", data={"content": "", "raw": payload})


# ---------------------------------------------------------------------------
# Codex parser
# ---------------------------------------------------------------------------


def parse_codex_event(line: str) -> AgentEvent | None:
    """Parse a single line of Codex CLI JSON output.

    Codex emits a similar newline-delimited JSON stream.  The exact schema
    differs slightly from Claude Code:

    * ``message`` -- text chunks
    * ``function_call`` / ``tool_call`` -- tool invocation
    * ``function_return`` / ``tool_return`` -- tool result
    * ``completed`` -- final result
    * ``error`` -- error

    Returns ``None`` for blank lines or unrecognised bookkeeping events.
    """
    stripped = line.strip()
    if not stripped:
        return None

    try:
        payload: dict[str, Any] = json.loads(stripped)
    except json.JSONDecodeError as exc:
        logger.debug("Codex: ignoring non-JSON line: %s", stripped[:120])
        return AgentEvent(
            type="error",
            data={"message": f"JSON parse error: {exc}", "raw_line": stripped[:500]},
        )

    event_type = payload.get("type", payload.get("event", ""))

    if event_type == "message":
        return AgentEvent(
            type="text",
            data={"content": payload.get("content", payload.get("text", ""))},
        )

    if event_type in ("function_call", "tool_call"):
        return AgentEvent(
            type="tool_call",
            data={
                "tool_name": payload.get("name", payload.get("function", "")),
                "tool_call_id": payload.get("call_id", payload.get("id", "")),
                "arguments": payload.get("arguments", {}),
            },
        )

    if event_type in ("function_return", "tool_return"):
        return AgentEvent(
            type="tool_result",
            data={
                "tool_call_id": payload.get("call_id", payload.get("id", "")),
                "output": payload.get("output", payload.get("result", "")),
                "is_error": payload.get("is_error", False),
            },
        )

    if event_type == "completed":
        return AgentEvent(
            type="done",
            data={
                "content": payload.get("response", payload.get("content", "")),
                "cost": payload.get("cost", None),
                "duration_ms": payload.get("duration_ms", None),
            },
        )

    if event_type == "error":
        return AgentEvent(
            type="error",
            data={
                "message": payload.get("message", payload.get("error", str(payload))),
            },
        )

    # Unknown or bookkeeping
    if event_type in ("status", "ping", "init", ""):
        return None

    logger.debug("Codex: unrecognised event type %r", event_type)
    return AgentEvent(type="text", data={"content": "", "raw": payload})
