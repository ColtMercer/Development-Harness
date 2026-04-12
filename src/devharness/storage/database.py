"""Database manager for SQLite.

Handles connection lifecycle, initialization, migrations, and backup.
Uses WAL mode for concurrent read/write support.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import aiosqlite

from devharness.storage.migrations.runner import run_migrations

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages the SQLite database lifecycle."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> aiosqlite.Connection:
        """Create the database file, run migrations, and return a connection."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(str(self.db_path))

        # Enable WAL mode for concurrent reads during writes
        await self._db.execute("PRAGMA journal_mode=WAL")
        # Enable foreign keys
        await self._db.execute("PRAGMA foreign_keys=ON")

        await run_migrations(self._db)
        logger.info("Database initialized at %s", self.db_path)
        return self._db

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._db

    async def close(self) -> None:
        """Close the database connection gracefully."""
        if self._db is not None:
            try:
                await self._db.close()
            except Exception:
                # aiosqlite can raise if the event loop is closing --
                # the connection thread races against loop shutdown.
                # This is harmless: SQLite handles unclean disconnects safely.
                pass
            self._db = None

    async def backup(self, dest: Path) -> None:
        """Create a hot backup of the database."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        # For aiosqlite, we use the file copy approach
        # (sqlite3 backup API requires sync access)
        await self.db.execute("BEGIN IMMEDIATE")
        try:
            shutil.copy2(self.db_path, dest)
            # Also copy WAL and SHM files if they exist
            for suffix in ("-wal", "-shm"):
                src = Path(str(self.db_path) + suffix)
                if src.exists():
                    shutil.copy2(src, Path(str(dest) + suffix))
        finally:
            await self.db.execute("ROLLBACK")
        logger.info("Database backed up to %s", dest)
