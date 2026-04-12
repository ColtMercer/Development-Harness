"""Memory service -- entry point for the memory subsystem.

Defines the abstract MemoryBackend interface and the MemoryService
facade that delegates to the configured backend with graceful
degradation when the backend is unavailable.
"""

from __future__ import annotations

import abc
import logging
from datetime import date
from typing import Any

from devharness.core.errors import MemoryUnavailableError

logger = logging.getLogger(__name__)


class MemoryBackend(abc.ABC):
    """Abstract base class for memory storage backends.

    Implementations include ObsidianMemoryBackend (Markdown + YAML)
    and potentially Neo4j or other graph databases.
    """

    @abc.abstractmethod
    async def ingest_event(self, event: dict[str, Any]) -> None:
        """Store an event in the memory backend."""

    @abc.abstractmethod
    async def query(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Run a structured query and return matching records."""

    @abc.abstractmethod
    async def search(self, text: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Full-text search across stored memories."""

    @abc.abstractmethod
    async def consolidate_daily(self, day: date | None = None) -> None:
        """Consolidate/summarise events for the given day."""

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Return True if the backend is reachable and healthy."""


class MemoryService:
    """Facade that delegates to a :class:`MemoryBackend`.

    If the backend is unavailable, every method degrades gracefully:
    writes are silently dropped, reads return empty results, and the
    caller is never interrupted by a backend failure.
    """

    def __init__(self, backend: MemoryBackend | None = None) -> None:
        self._backend = backend

    @property
    def available(self) -> bool:
        return self._backend is not None

    async def ingest_event(self, event: dict[str, Any]) -> None:
        if self._backend is None:
            return
        try:
            await self._backend.ingest_event(event)
        except Exception:
            logger.warning("Memory ingest failed; event dropped", exc_info=True)

    async def query(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        if self._backend is None:
            return []
        try:
            return await self._backend.query(query, **kwargs)
        except Exception:
            logger.warning("Memory query failed; returning empty", exc_info=True)
            return []

    async def search(self, text: str, *, limit: int = 10) -> list[dict[str, Any]]:
        if self._backend is None:
            return []
        try:
            return await self._backend.search(text, limit=limit)
        except Exception:
            logger.warning("Memory search failed; returning empty", exc_info=True)
            return []

    async def consolidate_daily(self, day: date | None = None) -> None:
        if self._backend is None:
            return
        try:
            await self._backend.consolidate_daily(day)
        except Exception:
            logger.warning("Memory consolidation failed", exc_info=True)

    async def health_check(self) -> bool:
        if self._backend is None:
            return False
        try:
            return await self._backend.health_check()
        except Exception:
            return False
