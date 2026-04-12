"""Artifact manager -- creates and indexes artifacts for a thread."""

from __future__ import annotations

import logging
from typing import Any

from devharness.core.event_bus import EventBus
from devharness.core.models import Artifact, ArtifactKind, Event, EventKind

logger = logging.getLogger(__name__)


class ArtifactManager:
    """Creates, stores, and queries artifacts.

    Artifacts are ephemeral within a session; persistence is delegated to
    the storage layer.  This manager keeps an in-memory index and emits
    ``ARTIFACT_CREATED`` events via the event bus.

    Parameters
    ----------
    event_bus:
        The shared event bus for emitting artifact events.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._artifacts: dict[str, Artifact] = {}  # keyed by artifact id
        self._thread_index: dict[str, list[str]] = {}  # thread_id -> [artifact_id]

    async def create(
        self,
        thread_id: str,
        turn_id: str | None,
        kind: ArtifactKind,
        name: str,
        content: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Artifact:
        """Create and register a new artifact.

        Parameters
        ----------
        thread_id:
            Owning thread.
        turn_id:
            The turn that produced this artifact (may be ``None``).
        kind:
            The artifact kind (patch, report, screenshot, ...).
        name:
            Human-readable name.
        content:
            Text content (for text-based artifacts).
        metadata:
            Arbitrary extra data attached to the artifact.

        Returns
        -------
        Artifact
            The created artifact.
        """
        artifact = Artifact(
            thread_id=thread_id,
            turn_id=turn_id,
            kind=kind,
            name=name,
            content=content,
            metadata=metadata or {},
        )

        self._artifacts[artifact.id] = artifact
        self._thread_index.setdefault(thread_id, []).append(artifact.id)

        await self._event_bus.emit(
            Event(
                thread_id=thread_id,
                turn_id=turn_id,
                kind=EventKind.ARTIFACT_CREATED,
                data={
                    "artifact_id": artifact.id,
                    "artifact_kind": kind.value,
                    "artifact_name": name,
                },
            )
        )

        logger.debug("Created artifact %s (%s) for thread %s", artifact.id, kind, thread_id)
        return artifact

    async def list_for_thread(self, thread_id: str) -> list[Artifact]:
        """Return all artifacts belonging to *thread_id*, ordered by creation time."""
        ids = self._thread_index.get(thread_id, [])
        artifacts = [self._artifacts[aid] for aid in ids if aid in self._artifacts]
        return sorted(artifacts, key=lambda a: a.created_at)

    def get(self, artifact_id: str) -> Artifact | None:
        """Return a single artifact by ID, or ``None`` if not found."""
        return self._artifacts.get(artifact_id)
