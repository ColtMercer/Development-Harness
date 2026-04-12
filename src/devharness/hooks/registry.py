"""Hook registry -- register, query, and discover hook configurations.

Hooks can be registered programmatically or discovered from the
``.devharness/hooks/`` directory inside a workspace.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from devharness.core.models import HookConfig, HookEvent

logger = logging.getLogger(__name__)


class HookRegistry:
    """In-memory registry of HookConfig objects."""

    def __init__(self) -> None:
        self._hooks: list[HookConfig] = []

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def register(self, config: HookConfig) -> None:
        """Register a hook configuration."""
        self._hooks.append(config)
        logger.debug("Registered hook %r for event %s", config.name, config.event)

    def get_hooks(self, event: HookEvent) -> list[HookConfig]:
        """Return all enabled hooks registered for *event*."""
        return [h for h in self._hooks if h.event == event and h.enabled]

    def list_hooks(self) -> list[HookConfig]:
        """Return all registered hooks."""
        return list(self._hooks)

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def load_from_directory(self, workspace_root: str) -> int:
        """Discover and register hooks from ``.devharness/hooks/``.

        Hook files are JSON files whose structure matches ``HookConfig``.
        Returns the number of hooks loaded.

        Each JSON file should contain either a single HookConfig dict or
        a list of HookConfig dicts.
        """
        hooks_dir = Path(workspace_root) / ".devharness" / "hooks"
        if not hooks_dir.is_dir():
            logger.debug("No hooks directory at %s", hooks_dir)
            return 0

        count = 0
        for path in sorted(hooks_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                configs: list[dict] = data if isinstance(data, list) else [data]
                for entry in configs:
                    hook = HookConfig.model_validate(entry)
                    self.register(hook)
                    count += 1
            except Exception as exc:
                logger.warning("Failed to load hook file %s: %s", path, exc)

        logger.info("Loaded %d hook(s) from %s", count, hooks_dir)
        return count
