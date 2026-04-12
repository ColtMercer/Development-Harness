"""Abstract base class for skills."""

from __future__ import annotations

from abc import ABC, abstractmethod

from devharness.core.models import SkillManifest


class BaseSkill(ABC):
    """A skill provides a system prompt, tool set, and verifier set.

    Skills are the primary unit of composition in the harness.  Each skill
    bundles a persona-level system prompt with the tools and verifiers that
    persona needs.  The :class:`SkillRegistry` combines multiple skills into
    a single agent configuration.
    """

    @property
    @abstractmethod
    def manifest(self) -> SkillManifest:
        """Return the skill's manifest metadata."""

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the full system prompt text for this skill."""

    def get_tool_names(self) -> list[str]:
        """Return the tool names this skill requires."""
        return list(self.manifest.tools)

    def get_verifier_names(self) -> list[str]:
        """Return the verifier names this skill registers."""
        return list(self.manifest.verifiers)

    # Convenience ---------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Skill {self.manifest.name} v{self.manifest.version}>"
