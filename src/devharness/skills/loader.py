"""Load skills from the filesystem.

Each skill directory must contain at least a ``manifest.yaml`` and an
optional ``prompt.md``.  The loader reads these files, validates the
manifest, and returns a concrete :class:`BaseSkill` instance.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from devharness.core.errors import SkillLoadError
from devharness.core.models import SkillManifest
from devharness.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class _DirectorySkill(BaseSkill):
    """Concrete skill loaded from a directory on disk."""

    def __init__(self, manifest: SkillManifest, prompt: str) -> None:
        self._manifest = manifest
        self._prompt = prompt

    @property
    def manifest(self) -> SkillManifest:
        return self._manifest

    def get_system_prompt(self) -> str:
        return self._prompt


class SkillLoader:
    """Discovers and loads skill directories."""

    # ------------------------------------------------------------------
    # Single-directory loading
    # ------------------------------------------------------------------

    @staticmethod
    def load_from_directory(path: Path) -> BaseSkill:
        """Load a single skill from *path*.

        The directory must contain ``manifest.yaml``.  An optional
        ``prompt.md`` provides the system prompt; if absent the
        ``system_prompt`` field in the manifest is used instead.

        Raises
        ------
        SkillLoadError
            If the manifest file is missing or invalid.
        """
        manifest_path = path / "manifest.yaml"
        if not manifest_path.exists():
            raise SkillLoadError(f"No manifest.yaml found in {path}")

        try:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SkillLoadError(f"Failed to parse {manifest_path}: {exc}") from exc

        if not isinstance(raw, dict):
            raise SkillLoadError(f"manifest.yaml in {path} is not a mapping")

        try:
            manifest = SkillManifest(**raw)
        except Exception as exc:
            raise SkillLoadError(
                f"Invalid manifest in {path}: {exc}"
            ) from exc

        # Load prompt from prompt.md, falling back to manifest field.
        prompt_path = path / "prompt.md"
        if prompt_path.exists():
            prompt = prompt_path.read_text(encoding="utf-8")
        else:
            prompt = manifest.system_prompt

        return _DirectorySkill(manifest=manifest, prompt=prompt)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    @classmethod
    def discover(cls, dirs: list[Path]) -> list[BaseSkill]:
        """Walk *dirs* looking for ``manifest.yaml`` files and load each.

        Directories that fail to load are logged as warnings and skipped.
        """
        skills: list[BaseSkill] = []
        for base in dirs:
            if not base.is_dir():
                logger.warning("Skill directory does not exist: %s", base)
                continue
            for child in sorted(base.iterdir()):
                if child.is_dir() and (child / "manifest.yaml").exists():
                    try:
                        skills.append(cls.load_from_directory(child))
                    except SkillLoadError:
                        logger.warning(
                            "Failed to load skill from %s", child, exc_info=True
                        )
        return skills
