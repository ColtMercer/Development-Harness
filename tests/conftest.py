"""Shared fixtures for the devharness test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from devharness.core.config import HarnessConfig
from devharness.core.event_bus import EventBus
from devharness.storage.sqlite import SqliteStorage


@pytest.fixture
def event_bus() -> EventBus:
    """Return a fresh EventBus instance."""
    return EventBus()


@pytest.fixture
def config(tmp_path: Path) -> HarnessConfig:
    """Return a HarnessConfig pointing at a temporary directory."""
    return HarnessConfig(
        storage_dir=tmp_path / ".devharness",
        db_path=tmp_path / "test_harness.db",
        log_level="DEBUG",
    )


@pytest.fixture
async def tmp_storage(tmp_path: Path) -> SqliteStorage:
    """Return an initialised SqliteStorage backed by a temp database."""
    db_path = tmp_path / "test.db"
    storage = SqliteStorage(db_path)
    await storage.initialize()
    yield storage  # type: ignore[misc]
    await storage.close()
