"""YAML frontmatter parsing and formatting.

Handles the ``---``-delimited YAML block at the top of Markdown files
used by Obsidian and other static-site generators.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n?(.*)",
    re.DOTALL,
)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from *text*.

    Returns
    -------
    tuple[dict, str]
        A two-tuple of ``(metadata_dict, body_content)``.
        If no frontmatter is present, ``metadata_dict`` is empty and
        ``body_content`` is the original *text*.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    yaml_block, body = match.group(1), match.group(2)
    try:
        metadata = yaml.safe_load(yaml_block)
    except yaml.YAMLError:
        return {}, text

    if not isinstance(metadata, dict):
        return {}, text

    return metadata, body


def format_frontmatter(metadata: dict[str, Any], content: str) -> str:
    """Format *metadata* and *content* into a Markdown string with YAML frontmatter.

    Parameters
    ----------
    metadata:
        Dict to serialize as the YAML frontmatter block.
    content:
        The Markdown body that follows the frontmatter.

    Returns
    -------
    str
        The complete document with ``---`` delimiters.
    """
    yaml_str = yaml.dump(metadata, default_flow_style=False, sort_keys=False).rstrip()
    return f"---\n{yaml_str}\n---\n{content}\n"
