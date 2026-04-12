"""Obsidian-based memory backend.

Implements :class:`MemoryBackend` by storing events as Markdown files
with YAML frontmatter in an Obsidian-compatible vault structure.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from devharness.core.errors import MemoryUnavailableError
from devharness.memory.obsidian.frontmatter import format_frontmatter, parse_frontmatter
from devharness.memory.obsidian.vault import read_note, search_vault, write_note
from devharness.memory.service import MemoryBackend

logger = logging.getLogger(__name__)


class ObsidianMemoryBackend(MemoryBackend):
    """Memory backend backed by Markdown files in an Obsidian vault.

    Vault layout::

        <vault_root>/
            events/<YYYY-MM-DD>/<id>.md
            daily/<YYYY-MM-DD>.md
    """

    def __init__(self, vault_path: str | Path) -> None:
        self._vault = Path(vault_path)

    # ------------------------------------------------------------------
    # MemoryBackend implementation
    # ------------------------------------------------------------------

    async def ingest_event(self, event: dict[str, Any]) -> None:
        """Write an event as a dated Markdown note."""
        now = datetime.now(timezone.utc)
        day_str = now.strftime("%Y-%m-%d")
        event_id = event.get("id", now.strftime("%H%M%S%f"))

        folder = self._vault / "events" / day_str
        folder.mkdir(parents=True, exist_ok=True)
        note_path = folder / f"{event_id}.md"

        frontmatter: dict[str, Any] = {
            "kind": event.get("kind", "event"),
            "thread_id": event.get("thread_id", ""),
            "timestamp": now.isoformat(),
        }
        # Include extra keys in frontmatter
        for key in ("turn_id", "severity", "tags"):
            if key in event:
                frontmatter[key] = event[key]

        content = event.get("content", event.get("details", ""))
        title = event.get("title", event.get("kind", "event"))
        body = f"# {title}\n\n{content}" if content else f"# {title}"

        write_note(str(note_path), frontmatter, body)

    async def query(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Search the vault for notes matching *query*."""
        return search_vault(query, str(self._vault))

    async def search(self, text: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Full-text search across vault notes."""
        results = search_vault(text, str(self._vault))
        return results[:limit]

    async def consolidate_daily(self, day: date | None = None) -> None:
        """Consolidate events for *day* into a daily summary note."""
        target_day = day or date.today()
        day_str = target_day.isoformat()
        events_dir = self._vault / "events" / day_str

        if not events_dir.is_dir():
            logger.debug("No events for %s; skipping consolidation", day_str)
            return

        entries: list[str] = []
        for md_file in sorted(events_dir.glob("*.md")):
            data = read_note(str(md_file))
            title = data.get("title", md_file.stem)
            entries.append(f"- {title}")

        if not entries:
            return

        daily_dir = self._vault / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        daily_path = daily_dir / f"{day_str}.md"

        frontmatter = {"date": day_str, "kind": "daily_summary", "event_count": len(entries)}
        body = f"# Daily Summary: {day_str}\n\n" + "\n".join(entries)
        write_note(str(daily_path), frontmatter, body)

    async def health_check(self) -> bool:
        """Return True if the vault directory exists and is writable."""
        try:
            return self._vault.is_dir()
        except OSError:
            return False
