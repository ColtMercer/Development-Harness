"""Tests for devharness.storage.sqlite.SqliteStorage."""

from __future__ import annotations

import pytest

from devharness.core.errors import StorageError, ThreadNotFoundError
from devharness.core.models import (
    Event,
    EventKind,
    Project,
    Thread,
    ThreadConfig,
    ThreadStatus,
)
from devharness.storage.sqlite import SqliteStorage


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------


class TestProjectCRUD:
    async def test_save_and_load_project(self, tmp_storage: SqliteStorage) -> None:
        project = Project(name="test-project", workspace_root="/tmp/ws")
        await tmp_storage.save_project(project)

        loaded = await tmp_storage.load_project(project.id)
        assert loaded.name == "test-project"
        assert loaded.workspace_root == "/tmp/ws"

    async def test_list_projects(self, tmp_storage: SqliteStorage) -> None:
        p1 = Project(name="alpha", workspace_root="/a")
        p2 = Project(name="beta", workspace_root="/b")
        await tmp_storage.save_project(p1)
        await tmp_storage.save_project(p2)

        projects = await tmp_storage.list_projects()
        names = [p.name for p in projects]
        assert "alpha" in names
        assert "beta" in names

    async def test_delete_project(self, tmp_storage: SqliteStorage) -> None:
        project = Project(name="to-delete", workspace_root="/tmp")
        await tmp_storage.save_project(project)
        await tmp_storage.delete_project(project.id)

        with pytest.raises(StorageError):
            await tmp_storage.load_project(project.id)

    async def test_update_project(self, tmp_storage: SqliteStorage) -> None:
        project = Project(name="original", workspace_root="/tmp")
        await tmp_storage.save_project(project)

        project.name = "updated"
        await tmp_storage.save_project(project)

        loaded = await tmp_storage.load_project(project.id)
        assert loaded.name == "updated"

    async def test_load_nonexistent_project(self, tmp_storage: SqliteStorage) -> None:
        with pytest.raises(StorageError):
            await tmp_storage.load_project("nonexistent")


# ---------------------------------------------------------------------------
# Thread CRUD
# ---------------------------------------------------------------------------


class TestThreadCRUD:
    async def test_save_and_load_thread(self, tmp_storage: SqliteStorage) -> None:
        thread = Thread(config=ThreadConfig(workspace_root="/ws"))
        await tmp_storage.save_thread(thread)

        loaded = await tmp_storage.load_thread(thread.id)
        assert loaded.id == thread.id
        assert loaded.config.workspace_root == "/ws"
        assert loaded.status == ThreadStatus.PENDING

    async def test_list_threads(self, tmp_storage: SqliteStorage) -> None:
        # Create projects first to satisfy foreign key constraints
        p1 = Project(id="p1", name="proj1", workspace_root="/a")
        p2 = Project(id="p2", name="proj2", workspace_root="/b")
        await tmp_storage.save_project(p1)
        await tmp_storage.save_project(p2)

        t1 = Thread(project_id="p1")
        t2 = Thread(project_id="p1")
        t3 = Thread(project_id="p2")
        await tmp_storage.save_thread(t1)
        await tmp_storage.save_thread(t2)
        await tmp_storage.save_thread(t3)

        all_threads = await tmp_storage.list_threads()
        assert len(all_threads) == 3

        p1_threads = await tmp_storage.list_threads(project_id="p1")
        assert len(p1_threads) == 2

    async def test_delete_thread(self, tmp_storage: SqliteStorage) -> None:
        thread = Thread()
        await tmp_storage.save_thread(thread)
        await tmp_storage.delete_thread(thread.id)

        with pytest.raises(ThreadNotFoundError):
            await tmp_storage.load_thread(thread.id)

    async def test_update_thread_status(self, tmp_storage: SqliteStorage) -> None:
        thread = Thread()
        await tmp_storage.save_thread(thread)

        thread.status = ThreadStatus.RUNNING
        await tmp_storage.save_thread(thread)

        loaded = await tmp_storage.load_thread(thread.id)
        assert loaded.status == ThreadStatus.RUNNING

    async def test_load_nonexistent_thread(self, tmp_storage: SqliteStorage) -> None:
        with pytest.raises(ThreadNotFoundError):
            await tmp_storage.load_thread("nonexistent")


# ---------------------------------------------------------------------------
# Event persistence
# ---------------------------------------------------------------------------


class TestEventPersistence:
    @staticmethod
    async def _ensure_thread(storage: SqliteStorage, thread_id: str) -> None:
        """Create a thread so foreign key constraints are satisfied."""
        thread = Thread(id=thread_id)
        await storage.save_thread(thread)

    async def test_save_and_load_event(self, tmp_storage: SqliteStorage) -> None:
        await self._ensure_thread(tmp_storage, "t1")
        event = Event(
            thread_id="t1",
            kind=EventKind.THREAD_CREATED,
            data={"key": "value"},
        )
        await tmp_storage.save_event(event)

        events = await tmp_storage.load_events("t1")
        assert len(events) == 1
        assert events[0].id == event.id
        assert events[0].kind == EventKind.THREAD_CREATED
        assert events[0].data == {"key": "value"}

    async def test_load_events_ordered(self, tmp_storage: SqliteStorage) -> None:
        await self._ensure_thread(tmp_storage, "t1")
        e1 = Event(thread_id="t1", kind=EventKind.THREAD_CREATED)
        e2 = Event(thread_id="t1", kind=EventKind.TURN_START)
        e3 = Event(thread_id="t1", kind=EventKind.TURN_END)
        await tmp_storage.save_event(e1)
        await tmp_storage.save_event(e2)
        await tmp_storage.save_event(e3)

        events = await tmp_storage.load_events("t1")
        assert len(events) == 3

    async def test_load_events_filtered_by_thread(
        self, tmp_storage: SqliteStorage
    ) -> None:
        await self._ensure_thread(tmp_storage, "t1")
        await self._ensure_thread(tmp_storage, "t2")
        await tmp_storage.save_event(
            Event(thread_id="t1", kind=EventKind.THREAD_CREATED)
        )
        await tmp_storage.save_event(
            Event(thread_id="t2", kind=EventKind.THREAD_CREATED)
        )

        t1_events = await tmp_storage.load_events("t1")
        assert len(t1_events) == 1
        assert t1_events[0].thread_id == "t1"

    async def test_load_events_empty(self, tmp_storage: SqliteStorage) -> None:
        events = await tmp_storage.load_events("nonexistent")
        assert events == []


# ---------------------------------------------------------------------------
# Settings get/set
# ---------------------------------------------------------------------------


class TestSettings:
    async def test_set_and_get_setting(self, tmp_storage: SqliteStorage) -> None:
        await tmp_storage.set_setting("theme", "dark")
        value = await tmp_storage.get_setting("theme")
        assert value == "dark"

    async def test_get_nonexistent_setting(self, tmp_storage: SqliteStorage) -> None:
        value = await tmp_storage.get_setting("nonexistent")
        assert value is None

    async def test_update_setting(self, tmp_storage: SqliteStorage) -> None:
        await tmp_storage.set_setting("key", "v1")
        await tmp_storage.set_setting("key", "v2")
        value = await tmp_storage.get_setting("key")
        assert value == "v2"

    async def test_multiple_settings(self, tmp_storage: SqliteStorage) -> None:
        await tmp_storage.set_setting("a", "1")
        await tmp_storage.set_setting("b", "2")
        assert await tmp_storage.get_setting("a") == "1"
        assert await tmp_storage.get_setting("b") == "2"


# ---------------------------------------------------------------------------
# Credential storage
# ---------------------------------------------------------------------------


class TestCredentials:
    async def test_save_and_load_credential(
        self, tmp_storage: SqliteStorage
    ) -> None:
        await tmp_storage.save_credential("proj1", "openai", "api_key", "sk-123")
        value = await tmp_storage.load_credential("proj1", "openai", "api_key")
        assert value == "sk-123"

    async def test_load_nonexistent_credential(
        self, tmp_storage: SqliteStorage
    ) -> None:
        value = await tmp_storage.load_credential("proj1", "openai", "api_key")
        assert value is None

    async def test_global_credential(self, tmp_storage: SqliteStorage) -> None:
        await tmp_storage.save_credential(None, "anthropic", "key", "sk-abc")
        value = await tmp_storage.load_credential(None, "anthropic", "key")
        assert value == "sk-abc"

    async def test_update_credential(self, tmp_storage: SqliteStorage) -> None:
        await tmp_storage.save_credential("p1", "provider", "key", "old")
        await tmp_storage.save_credential("p1", "provider", "key", "new")
        value = await tmp_storage.load_credential("p1", "provider", "key")
        assert value == "new"


# ---------------------------------------------------------------------------
# Turn context save/load
# ---------------------------------------------------------------------------


class TestTurnContext:
    async def test_save_and_load_turn_context(
        self, tmp_storage: SqliteStorage
    ) -> None:
        ctx = {"messages": [{"role": "user", "content": "hello"}], "step": 3}
        await tmp_storage.save_turn_context("t1", "turn1", ctx)

        loaded = await tmp_storage.load_turn_context("t1", "turn1")
        assert loaded is not None
        assert loaded["step"] == 3
        assert loaded["messages"][0]["content"] == "hello"

    async def test_load_nonexistent_turn_context(
        self, tmp_storage: SqliteStorage
    ) -> None:
        result = await tmp_storage.load_turn_context("t1", "nonexistent")
        assert result is None

    async def test_update_turn_context(self, tmp_storage: SqliteStorage) -> None:
        await tmp_storage.save_turn_context("t1", "turn1", {"v": 1})
        await tmp_storage.save_turn_context("t1", "turn1", {"v": 2})
        loaded = await tmp_storage.load_turn_context("t1", "turn1")
        assert loaded is not None
        assert loaded["v"] == 2
