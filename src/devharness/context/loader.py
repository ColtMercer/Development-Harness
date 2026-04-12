"""Context file and skill prompt loader.

Reads context files (CLAUDE.md, AGENTS.md, etc.) from the workspace and
loads skill prompts from the skill registry, handling missing files and
skills gracefully.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from devharness.core.models import SkillManifest

logger = logging.getLogger(__name__)


class SkillRegistry(Protocol):
    """Minimal interface expected from a skill registry."""

    def get(self, name: str) -> SkillManifest | None: ...


def load_context_files(
    paths: list[str],
    workspace_root: str,
) -> list[str]:
    """Load context files from the workspace.

    Each path is resolved relative to *workspace_root*.  Missing files
    are silently skipped with a debug log.

    Returns a list of file contents (one string per successfully loaded file).
    """
    root = Path(workspace_root)
    contents: list[str] = []

    for rel_path in paths:
        full_path = root / rel_path
        try:
            text = full_path.read_text(encoding="utf-8")
            if text.strip():
                contents.append(text)
        except FileNotFoundError:
            logger.debug("Context file not found, skipping: %s", full_path)
        except OSError as exc:
            logger.warning("Failed to read context file %s: %s", full_path, exc)

    return contents


def load_skill_prompts(
    skill_names: list[str],
    skill_registry: SkillRegistry,
) -> list[str]:
    """Load system prompts from skill manifests.

    Missing or prompt-less skills are silently skipped.

    Returns a list of skill prompt strings.
    """
    prompts: list[str] = []

    for name in skill_names:
        manifest = skill_registry.get(name)
        if manifest is None:
            logger.debug("Skill not found in registry, skipping: %s", name)
            continue
        if manifest.system_prompt:
            prompts.append(manifest.system_prompt)

    return prompts
