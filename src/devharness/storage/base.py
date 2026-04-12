"""Abstract storage backend interface.

The storage layer handles all persistence. The SQLite implementation
is the primary backend. All methods are async to support non-blocking I/O.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from devharness.core.models import (
    Artifact,
    Checkpoint,
    Event,
    Observation,
    Project,
    Thread,
)


class StorageBackend(ABC):
    """Abstract interface for harness persistence."""

    # --- Projects ---

    @abstractmethod
    async def save_project(self, project: Project) -> None: ...

    @abstractmethod
    async def load_project(self, project_id: str) -> Project: ...

    @abstractmethod
    async def list_projects(self) -> list[Project]: ...

    @abstractmethod
    async def delete_project(self, project_id: str) -> None: ...

    # --- Threads ---

    @abstractmethod
    async def save_thread(self, thread: Thread) -> None: ...

    @abstractmethod
    async def load_thread(self, thread_id: str) -> Thread: ...

    @abstractmethod
    async def list_threads(self, project_id: str | None = None) -> list[Thread]: ...

    @abstractmethod
    async def delete_thread(self, thread_id: str) -> None: ...

    # --- Events ---

    @abstractmethod
    async def save_event(self, event: Event) -> None: ...

    @abstractmethod
    async def load_events(self, thread_id: str) -> list[Event]: ...

    # --- Observations ---

    @abstractmethod
    async def save_observation(self, observation: Observation) -> None: ...

    @abstractmethod
    async def load_observations(self, thread_id: str) -> list[Observation]: ...

    # --- Artifacts ---

    @abstractmethod
    async def save_artifact(self, artifact: Artifact) -> None: ...

    @abstractmethod
    async def load_artifacts(self, thread_id: str) -> list[Artifact]: ...

    @abstractmethod
    async def load_artifact(self, artifact_id: str) -> Artifact: ...

    # --- Checkpoints ---

    @abstractmethod
    async def save_checkpoint(self, checkpoint: Checkpoint) -> None: ...

    @abstractmethod
    async def load_checkpoint(self, thread_id: str) -> Checkpoint | None: ...

    # --- Turn context (for approval pause/resume) ---

    @abstractmethod
    async def save_turn_context(
        self, thread_id: str, turn_id: str, context: dict
    ) -> None: ...

    @abstractmethod
    async def load_turn_context(
        self, thread_id: str, turn_id: str
    ) -> dict | None: ...

    # --- Settings (key-value) ---

    @abstractmethod
    async def get_setting(self, key: str) -> str | None: ...

    @abstractmethod
    async def set_setting(self, key: str, value: str) -> None: ...

    # --- Credentials (encrypted) ---

    @abstractmethod
    async def save_credential(
        self, project_id: str | None, provider: str, key_name: str, value: str
    ) -> None: ...

    @abstractmethod
    async def load_credential(
        self, project_id: str | None, provider: str, key_name: str
    ) -> str | None: ...

    # --- Memory event buffer (for Neo4j graceful degradation) ---

    @abstractmethod
    async def buffer_memory_event(
        self, event_type: str, event_data: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    async def drain_memory_buffer(self, limit: int = 100) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def mark_buffer_sent(self, event_ids: list[int]) -> None: ...

    # --- Lifecycle ---

    @abstractmethod
    async def initialize(self) -> None:
        """Create tables / run migrations. Called once at startup."""

    @abstractmethod
    async def close(self) -> None:
        """Close connections. Called at shutdown."""
