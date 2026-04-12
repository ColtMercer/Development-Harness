"""SQLite storage backend implementation.

This is the primary storage backend for the harness. All structured data
(threads, events, observations, config, credentials) lives in a single
SQLite database file.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from devharness.core.errors import StorageError, ThreadNotFoundError
from devharness.core.models import (
    Artifact,
    Checkpoint,
    Event,
    Observation,
    Project,
    Thread,
    ThreadConfig,
)
from devharness.storage.base import StorageBackend
from devharness.storage.database import DatabaseManager

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteStorage(StorageBackend):
    """SQLite-backed storage for all harness data."""

    def __init__(self, db_path: Path) -> None:
        self._db_manager = DatabaseManager(db_path)
        self._db: aiosqlite.Connection | None = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Storage not initialized. Call initialize() first.")
        return self._db

    async def initialize(self) -> None:
        self._db = await self._db_manager.initialize()

    async def close(self) -> None:
        await self._db_manager.close()
        self._db = None

    # --- Projects ---

    async def save_project(self, project: Project) -> None:
        config_json = project.model_dump_json(
            exclude={"id", "name", "workspace_root", "created_at", "updated_at"}
        )
        await self.db.execute(
            """
            INSERT INTO projects (id, name, workspace_root, config_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                workspace_root=excluded.workspace_root,
                config_json=excluded.config_json,
                updated_at=excluded.updated_at
            """,
            (
                project.id,
                project.name,
                project.workspace_root,
                config_json,
                project.created_at.isoformat(),
                _now_iso(),
            ),
        )
        await self.db.commit()

    async def load_project(self, project_id: str) -> Project:
        cursor = await self.db.execute(
            "SELECT id, name, workspace_root, config_json, created_at, updated_at FROM projects WHERE id = ?",
            (project_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise StorageError(f"Project not found: {project_id}")
        config = json.loads(row[3])
        return Project(
            id=row[0],
            name=row[1],
            workspace_root=row[2],
            created_at=datetime.fromisoformat(row[4]),
            updated_at=datetime.fromisoformat(row[5]),
            **config,
        )

    async def list_projects(self) -> list[Project]:
        cursor = await self.db.execute(
            "SELECT id, name, workspace_root, config_json, created_at, updated_at FROM projects ORDER BY name"
        )
        rows = await cursor.fetchall()
        projects = []
        for row in rows:
            config = json.loads(row[3])
            projects.append(
                Project(
                    id=row[0],
                    name=row[1],
                    workspace_root=row[2],
                    created_at=datetime.fromisoformat(row[4]),
                    updated_at=datetime.fromisoformat(row[5]),
                    **config,
                )
            )
        return projects

    async def delete_project(self, project_id: str) -> None:
        await self.db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await self.db.commit()

    # --- Threads ---

    async def save_thread(self, thread: Thread) -> None:
        thread_json = thread.model_dump_json()
        config_json = thread.config.model_dump_json()
        await self.db.execute(
            """
            INSERT INTO threads (id, project_id, status, config_json, thread_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                config_json=excluded.config_json,
                thread_json=excluded.thread_json,
                updated_at=excluded.updated_at
            """,
            (
                thread.id,
                thread.project_id,
                thread.status.value,
                config_json,
                thread_json,
                thread.created_at.isoformat(),
                _now_iso(),
            ),
        )
        await self.db.commit()

    async def load_thread(self, thread_id: str) -> Thread:
        cursor = await self.db.execute(
            "SELECT thread_json FROM threads WHERE id = ?", (thread_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise ThreadNotFoundError(f"Thread not found: {thread_id}")
        return Thread.model_validate_json(row[0])

    async def list_threads(self, project_id: str | None = None) -> list[Thread]:
        if project_id:
            cursor = await self.db.execute(
                "SELECT thread_json FROM threads WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
        else:
            cursor = await self.db.execute(
                "SELECT thread_json FROM threads ORDER BY created_at DESC"
            )
        rows = await cursor.fetchall()
        return [Thread.model_validate_json(row[0]) for row in rows]

    async def delete_thread(self, thread_id: str) -> None:
        await self.db.execute("DELETE FROM events WHERE thread_id = ?", (thread_id,))
        await self.db.execute(
            "DELETE FROM observations WHERE thread_id = ?", (thread_id,)
        )
        await self.db.execute(
            "DELETE FROM artifacts WHERE thread_id = ?", (thread_id,)
        )
        await self.db.execute(
            "DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,)
        )
        await self.db.execute(
            "DELETE FROM turn_contexts WHERE thread_id = ?", (thread_id,)
        )
        await self.db.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
        await self.db.commit()

    # --- Events ---

    async def save_event(self, event: Event) -> None:
        await self.db.execute(
            """
            INSERT OR IGNORE INTO events (id, thread_id, turn_id, kind, data_json, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.thread_id,
                event.turn_id,
                event.kind.value,
                json.dumps(event.data),
                event.timestamp.isoformat(),
            ),
        )
        await self.db.commit()

    async def load_events(self, thread_id: str) -> list[Event]:
        cursor = await self.db.execute(
            "SELECT id, thread_id, turn_id, kind, data_json, timestamp FROM events WHERE thread_id = ? ORDER BY timestamp",
            (thread_id,),
        )
        rows = await cursor.fetchall()
        return [
            Event(
                id=row[0],
                thread_id=row[1],
                turn_id=row[2],
                kind=row[3],
                data=json.loads(row[4]),
                timestamp=datetime.fromisoformat(row[5]),
            )
            for row in rows
        ]

    # --- Observations ---

    async def save_observation(self, observation: Observation) -> None:
        await self.db.execute(
            """
            INSERT OR IGNORE INTO observations
            (id, thread_id, turn_id, observer_name, severity, title, details, data_json, timestamp, source_file, source_line)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.id,
                observation.thread_id,
                observation.turn_id,
                observation.observer_name,
                observation.severity.value,
                observation.title,
                observation.details,
                json.dumps(observation.data),
                observation.timestamp.isoformat(),
                observation.source_file,
                observation.source_line,
            ),
        )
        await self.db.commit()

    async def load_observations(self, thread_id: str) -> list[Observation]:
        cursor = await self.db.execute(
            "SELECT id, thread_id, turn_id, observer_name, severity, title, details, data_json, timestamp, source_file, source_line "
            "FROM observations WHERE thread_id = ? ORDER BY timestamp",
            (thread_id,),
        )
        rows = await cursor.fetchall()
        return [
            Observation(
                id=row[0],
                thread_id=row[1],
                turn_id=row[2],
                observer_name=row[3],
                severity=row[4],
                title=row[5],
                details=row[6],
                data=json.loads(row[7]),
                timestamp=datetime.fromisoformat(row[8]),
                source_file=row[9],
                source_line=row[10],
            )
            for row in rows
        ]

    # --- Artifacts ---

    async def save_artifact(self, artifact: Artifact) -> None:
        await self.db.execute(
            """
            INSERT OR IGNORE INTO artifacts
            (id, thread_id, turn_id, kind, name, content, file_path, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.id,
                artifact.thread_id,
                artifact.turn_id,
                artifact.kind.value,
                artifact.name,
                artifact.content,
                artifact.file_path,
                json.dumps(artifact.metadata),
                artifact.created_at.isoformat(),
            ),
        )
        await self.db.commit()

    async def load_artifacts(self, thread_id: str) -> list[Artifact]:
        cursor = await self.db.execute(
            "SELECT id, thread_id, turn_id, kind, name, content, file_path, metadata_json, created_at "
            "FROM artifacts WHERE thread_id = ? ORDER BY created_at",
            (thread_id,),
        )
        rows = await cursor.fetchall()
        return [
            Artifact(
                id=row[0],
                thread_id=row[1],
                turn_id=row[2],
                kind=row[3],
                name=row[4],
                content=row[5],
                file_path=row[6],
                metadata=json.loads(row[7]),
                created_at=datetime.fromisoformat(row[8]),
            )
            for row in rows
        ]

    async def load_artifact(self, artifact_id: str) -> Artifact:
        cursor = await self.db.execute(
            "SELECT id, thread_id, turn_id, kind, name, content, file_path, metadata_json, created_at "
            "FROM artifacts WHERE id = ?",
            (artifact_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise StorageError(f"Artifact not found: {artifact_id}")
        return Artifact(
            id=row[0],
            thread_id=row[1],
            turn_id=row[2],
            kind=row[3],
            name=row[4],
            content=row[5],
            file_path=row[6],
            metadata=json.loads(row[7]),
            created_at=datetime.fromisoformat(row[8]),
        )

    # --- Checkpoints ---

    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        await self.db.execute(
            "INSERT INTO checkpoints (thread_id, snapshot_json, saved_at) VALUES (?, ?, ?)",
            (
                checkpoint.thread_id,
                checkpoint.model_dump_json(),
                checkpoint.saved_at.isoformat(),
            ),
        )
        await self.db.commit()

    async def load_checkpoint(self, thread_id: str) -> Checkpoint | None:
        cursor = await self.db.execute(
            "SELECT snapshot_json FROM checkpoints WHERE thread_id = ? ORDER BY saved_at DESC LIMIT 1",
            (thread_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return Checkpoint.model_validate_json(row[0])

    # --- Turn contexts ---

    async def save_turn_context(
        self, thread_id: str, turn_id: str, context: dict
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO turn_contexts (thread_id, turn_id, context_json, saved_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(thread_id, turn_id) DO UPDATE SET
                context_json=excluded.context_json,
                saved_at=excluded.saved_at
            """,
            (thread_id, turn_id, json.dumps(context), _now_iso()),
        )
        await self.db.commit()

    async def load_turn_context(
        self, thread_id: str, turn_id: str
    ) -> dict | None:
        cursor = await self.db.execute(
            "SELECT context_json FROM turn_contexts WHERE thread_id = ? AND turn_id = ?",
            (thread_id, turn_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    # --- Settings ---

    async def get_setting(self, key: str) -> str | None:
        cursor = await self.db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await self.db.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, value, _now_iso()),
        )
        await self.db.commit()

    # --- Credentials ---

    async def save_credential(
        self, project_id: str | None, provider: str, key_name: str, value: str
    ) -> None:
        # In a production system, value would be encrypted.
        # For now, we store plaintext in a local-only DB file that's .gitignored.
        await self.db.execute(
            """
            INSERT INTO credentials (project_id, provider, key_name, encrypted_value, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id, provider, key_name) DO UPDATE SET
                encrypted_value=excluded.encrypted_value
            """,
            (project_id, provider, key_name, value, _now_iso()),
        )
        await self.db.commit()

    async def load_credential(
        self, project_id: str | None, provider: str, key_name: str
    ) -> str | None:
        if project_id:
            cursor = await self.db.execute(
                "SELECT encrypted_value FROM credentials WHERE project_id = ? AND provider = ? AND key_name = ?",
                (project_id, provider, key_name),
            )
        else:
            cursor = await self.db.execute(
                "SELECT encrypted_value FROM credentials WHERE project_id IS NULL AND provider = ? AND key_name = ?",
                (provider, key_name),
            )
        row = await cursor.fetchone()
        return row[0] if row else None

    # --- Memory event buffer ---

    async def buffer_memory_event(
        self, event_type: str, event_data: dict[str, Any]
    ) -> None:
        await self.db.execute(
            "INSERT INTO memory_event_buffer (event_type, event_data, created_at) VALUES (?, ?, ?)",
            (event_type, json.dumps(event_data), _now_iso()),
        )
        await self.db.commit()

    async def drain_memory_buffer(self, limit: int = 100) -> list[dict[str, Any]]:
        cursor = await self.db.execute(
            "SELECT id, event_type, event_data FROM memory_event_buffer WHERE status = 'pending' ORDER BY id LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [
            {"id": row[0], "event_type": row[1], "event_data": json.loads(row[2])}
            for row in rows
        ]

    async def mark_buffer_sent(self, event_ids: list[int]) -> None:
        if not event_ids:
            return
        placeholders = ",".join("?" * len(event_ids))
        await self.db.execute(
            f"UPDATE memory_event_buffer SET status = 'sent' WHERE id IN ({placeholders})",
            event_ids,
        )
        await self.db.commit()
