"""Simple SQL migration runner.

Migrations are numbered SQL files (001_initial.sql, 002_add_hooks.sql, etc.).
The runner applies them in order, tracking which have been applied in the
schema_version table.
"""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent


async def run_migrations(db: aiosqlite.Connection) -> None:
    """Apply all pending migrations in order."""
    # Ensure schema_version table exists (bootstrap)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    await db.commit()

    # Get current version
    cursor = await db.execute("SELECT MAX(version) FROM schema_version")
    row = await cursor.fetchone()
    current_version = row[0] if row[0] is not None else 0

    # Find and apply pending migrations
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    for migration_file in migration_files:
        # Extract version number from filename (e.g., "001_initial.sql" -> 1)
        version_str = migration_file.stem.split("_")[0]
        try:
            version = int(version_str)
        except ValueError:
            logger.warning("Skipping non-numbered migration: %s", migration_file.name)
            continue

        if version <= current_version:
            continue

        logger.info("Applying migration %d: %s", version, migration_file.name)
        sql = migration_file.read_text()

        await db.executescript(sql)
        await db.commit()

        logger.info("Migration %d applied successfully", version)
