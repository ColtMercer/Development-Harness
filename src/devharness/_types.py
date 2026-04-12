"""Shared type aliases used across the harness."""

from __future__ import annotations

from typing import Any

# JSON-compatible dictionary
JsonDict = dict[str, Any]

# Event handler callback
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from devharness.core.models import Event

    EventHandler = Callable[[Event], Awaitable[None]]
