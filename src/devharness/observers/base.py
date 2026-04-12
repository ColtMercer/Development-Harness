"""Base observer interface.

Observers watch aspects of the application being developed and produce
structured Observation objects that get injected into the agent's context.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from devharness.core.models import Observation, Thread, Turn


class BaseObserver(ABC):
    """Abstract interface for application observers."""

    name: str

    @abstractmethod
    async def observe(self, thread: Thread, turn: Turn | None = None) -> list[Observation]:
        """Run observation and return findings.

        Returns an empty list if nothing noteworthy was detected.
        """

    @abstractmethod
    async def start(self) -> None:
        """Start any continuous monitoring (e.g., process watching, log tailing)."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop continuous monitoring and clean up resources."""

    @property
    def is_running(self) -> bool:
        """Whether continuous monitoring is active."""
        return False
