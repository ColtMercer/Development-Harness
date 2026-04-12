"""Skill registry -- central catalogue of available skills."""

from __future__ import annotations

import logging

from devharness.core.errors import SkillNotFoundError
from devharness.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Thread-safe registry of loaded skills.

    Skills are keyed by their manifest name.  Duplicate registrations
    overwrite the previous entry (useful for reloading).
    """

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register(self, skill: BaseSkill) -> None:
        """Register a skill (or replace an existing one with the same name)."""
        name = skill.manifest.name
        if name in self._skills:
            logger.info("Replacing skill %r", name)
        self._skills[name] = skill

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def get(self, name: str) -> BaseSkill:
        """Return a skill by name.

        Raises
        ------
        SkillNotFoundError
            If no skill with *name* is registered.
        """
        try:
            return self._skills[name]
        except KeyError:
            raise SkillNotFoundError(f"Skill not found: {name}") from None

    def list_skills(self) -> list[BaseSkill]:
        """Return all registered skills in alphabetical order."""
        return sorted(self._skills.values(), key=lambda s: s.manifest.name)

    def get_combined_system_prompt(self, skill_names: list[str]) -> str:
        """Concatenate system prompts for the given skill names.

        Each skill's prompt is separated by a horizontal rule.  Skills
        that are not found raise :class:`SkillNotFoundError`.
        """
        sections: list[str] = []
        for name in skill_names:
            skill = self.get(name)
            prompt = skill.get_system_prompt()
            if prompt:
                sections.append(prompt)
        return "\n\n---\n\n".join(sections)

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, name: str) -> bool:
        return name in self._skills
