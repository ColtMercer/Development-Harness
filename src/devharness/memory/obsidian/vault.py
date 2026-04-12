"""Vault file management for the Obsidian memory backend.

Low-level helpers for reading, writing, and searching Markdown notes
with YAML frontmatter in an Obsidian vault directory.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from devharness.memory.obsidian.frontmatter import format_frontmatter, parse_frontmatter

logger = logging.getLogger(__name__)


def write_note(path: str, frontmatter: dict[str, Any], content: str) -> None:
    """Write a Markdown note with YAML frontmatter.

    Creates parent directories as needed.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = format_frontmatter(frontmatter, content)
    p.write_text(text, encoding="utf-8")


def read_note(path: str) -> dict[str, Any]:
    """Read a Markdown note and return parsed frontmatter + content.

    Returns a dict with all frontmatter keys plus ``"content"`` for the
    body text and ``"_path"`` for the file path.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Note not found: {path}")

    raw = p.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(raw)
    metadata["content"] = body
    metadata["_path"] = str(p)

    # Extract title from first ``# heading`` if present
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            metadata.setdefault("title", stripped[2:].strip())
            break

    return metadata


def search_vault(query: str, vault_path: str) -> list[dict[str, Any]]:
    """Simple full-text search across all ``.md`` files in *vault_path*.

    Returns a list of dicts (same shape as :func:`read_note`) for notes
    whose content or frontmatter contains *query* (case-insensitive).
    """
    root = Path(vault_path)
    if not root.is_dir():
        return []

    query_lower = query.lower()
    results: list[dict[str, Any]] = []

    for md_file in root.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError:
            continue
        if query_lower in text.lower():
            try:
                note = read_note(str(md_file))
                results.append(note)
            except Exception:
                logger.debug("Failed to parse %s during search", md_file)

    return results
