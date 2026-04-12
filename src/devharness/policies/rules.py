"""Built-in policy rules that can deny specific tool invocations."""

from __future__ import annotations

import fnmatch
import re
from abc import ABC, abstractmethod
from typing import Any

from devharness.core.models import ApprovalMode, PolicyDecision, ToolCategory


class PolicyRule(ABC):
    """Abstract base for a single policy rule."""

    name: str

    @abstractmethod
    def evaluate(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        category: ToolCategory,
    ) -> PolicyDecision | None:
        """Return a *deny* PolicyDecision, or ``None`` to abstain."""


# ---------------------------------------------------------------------------
# Concrete rules
# ---------------------------------------------------------------------------


class DenyPathPatternRule(PolicyRule):
    """Deny writes to file paths matching one or more glob patterns.

    Inspects common argument names (``path``, ``file_path``, ``file``) to find
    the target path and matches it against the configured patterns.
    """

    name = "deny_path_pattern"

    def __init__(self, patterns: list[str] | None = None) -> None:
        self.patterns = patterns or ["**/.env", "**/.env.*", "**/credentials*", "**/secrets*"]

    def evaluate(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        category: ToolCategory,
    ) -> PolicyDecision | None:
        if category != ToolCategory.WRITE:
            return None

        target = arguments.get("path") or arguments.get("file_path") or arguments.get("file")
        if not isinstance(target, str):
            return None

        for pattern in self.patterns:
            if fnmatch.fnmatch(target, pattern):
                return PolicyDecision(
                    allowed=False,
                    mode=ApprovalMode.AUTO_APPROVE_SAFE,
                    reason=f"Path '{target}' matches denied pattern '{pattern}'.",
                )
        return None


class DenyCommandRule(PolicyRule):
    """Deny shell commands matching dangerous patterns."""

    name = "deny_command"

    DEFAULT_PATTERNS = [
        r"\brm\s+-rf\s+/",
        r"\bsudo\b",
        r"\bchmod\s+777\b",
        r"\bmkfs\b",
        r"\bdd\s+if=",
    ]

    def __init__(self, patterns: list[str] | None = None) -> None:
        raw = patterns or self.DEFAULT_PATTERNS
        self._compiled = [re.compile(p) for p in raw]
        self._raw = raw

    def evaluate(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        category: ToolCategory,
    ) -> PolicyDecision | None:
        if tool_name != "shell":
            return None

        command = arguments.get("command", "")
        if not isinstance(command, str):
            return None

        for regex, raw in zip(self._compiled, self._raw):
            if regex.search(command):
                return PolicyDecision(
                    allowed=False,
                    mode=ApprovalMode.AUTO_APPROVE_SAFE,
                    reason=f"Command matches denied pattern '{raw}'.",
                )
        return None


class MaxFileSizeRule(PolicyRule):
    """Deny writes where the content exceeds a byte-size threshold."""

    name = "max_file_size"

    def __init__(self, max_bytes: int = 1_000_000) -> None:
        self.max_bytes = max_bytes

    def evaluate(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        category: ToolCategory,
    ) -> PolicyDecision | None:
        if category != ToolCategory.WRITE:
            return None

        content = arguments.get("content")
        if not isinstance(content, str):
            return None

        size = len(content.encode("utf-8"))
        if size > self.max_bytes:
            return PolicyDecision(
                allowed=False,
                mode=ApprovalMode.AUTO_APPROVE_SAFE,
                reason=(
                    f"Content size ({size} bytes) exceeds maximum "
                    f"allowed ({self.max_bytes} bytes)."
                ),
            )
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def default_rules() -> list[PolicyRule]:
    """Return the set of built-in rules with default configuration."""
    return [
        DenyPathPatternRule(),
        DenyCommandRule(),
        MaxFileSizeRule(),
    ]


def apply_rules(
    rules: list[PolicyRule],
    tool_name: str,
    arguments: dict[str, Any],
    category: ToolCategory,
) -> PolicyDecision | None:
    """Run all *rules* in order; return the first deny decision or ``None``."""
    for rule in rules:
        decision = rule.evaluate(tool_name, arguments, category)
        if decision is not None and not decision.allowed:
            return decision
    return None
