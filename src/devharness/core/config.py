"""Harness configuration loading.

DB-FIRST DESIGN: All configuration lives in the SQLite database settings table.
The only env var needed is DEVHARNESS_STORAGE_DIR to locate the database.
Everything else is stored in DB, configurable via CLI and UI.

Loading order:
1. Hard-coded defaults (in HarnessConfig)
2. Database settings table (overrides defaults)
3. DEVHARNESS_STORAGE_DIR env var (only bootstrap var -- locates the DB)

API keys are stored in the credentials table, not settings.
The agent can manage its own config via `harness config set`.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from devharness.core.models import ApprovalMode

logger = logging.getLogger(__name__)

# The ONLY env var the harness reads. Everything else is in the DB.
STORAGE_DIR_ENV = "DEVHARNESS_STORAGE_DIR"


class HarnessConfig(BaseModel):
    """Top-level harness configuration.

    All fields have sensible defaults. Values are overridden by the DB
    settings table at startup. No env vars needed beyond DEVHARNESS_STORAGE_DIR.
    """

    # Bootstrap (the only thing that CAN'T be in the DB -- you need it to find the DB)
    storage_dir: Path = Path(".devharness")
    db_path: Path | None = None

    # Server
    server_host: str = "127.0.0.1"
    server_port: int = 8390

    # Defaults
    default_approval_mode: ApprovalMode = ApprovalMode.AUTO_APPROVE_SAFE
    default_agent_backend: str = "claude-code"
    default_memory_backend: str = "none"  # "neo4j" | "obsidian" | "none"

    # Skills
    skills_dirs: list[Path] = Field(default_factory=lambda: [Path("skills")])

    # Logging
    log_level: str = "INFO"

    # Neo4j (optional)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_database: str = "harness"
    neo4j_username: str = "neo4j"
    neo4j_enabled: bool = False

    # Obsidian (optional)
    obsidian_vault_path: Path = Path(".devharness/vault")

    # Embeddings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Consolidation
    consolidation_schedule: str = "0 3 * * *"

    def get_db_path(self) -> Path:
        if self.db_path:
            return self.db_path
        return self.storage_dir / "harness.db"


# --- Settings key registry ---
# Maps DB settings keys to config fields.
# This is the canonical list of what can be configured via CLI/UI/agent.

SETTINGS_KEYS: dict[str, dict[str, Any]] = {
    "server.host": {"field": "server_host", "type": "str", "description": "Server bind address"},
    "server.port": {"field": "server_port", "type": "int", "description": "Server port"},
    "default.approval_mode": {"field": "default_approval_mode", "type": "str", "description": "Default approval mode (full_trust, auto_approve_safe, approval_required, read_only, workspace_write)"},
    "default.agent_backend": {"field": "default_agent_backend", "type": "str", "description": "Default agent backend (claude-code, codex)"},
    "default.memory_backend": {"field": "default_memory_backend", "type": "str", "description": "Memory backend (none, neo4j, obsidian)"},
    "log.level": {"field": "log_level", "type": "str", "description": "Logging level (DEBUG, INFO, WARNING, ERROR)"},
    "neo4j.uri": {"field": "neo4j_uri", "type": "str", "description": "Neo4j connection URI"},
    "neo4j.database": {"field": "neo4j_database", "type": "str", "description": "Neo4j database name"},
    "neo4j.username": {"field": "neo4j_username", "type": "str", "description": "Neo4j username"},
    "neo4j.enabled": {"field": "neo4j_enabled", "type": "bool", "description": "Enable Neo4j memory backend"},
    "obsidian.vault_path": {"field": "obsidian_vault_path", "type": "path", "description": "Obsidian vault directory path"},
    "embedding.model": {"field": "embedding_model", "type": "str", "description": "Embedding model for vector search"},
    "embedding.dimensions": {"field": "embedding_dimensions", "type": "int", "description": "Embedding vector dimensions"},
    "consolidation.schedule": {"field": "consolidation_schedule", "type": "str", "description": "Daily consolidation cron schedule"},
}

# Credential keys (stored in credentials table, not settings)
CREDENTIAL_KEYS: dict[str, dict[str, str]] = {
    "anthropic.api_key": {"provider": "anthropic", "key_name": "api_key", "description": "Anthropic API key (for Claude Code)"},
    "openai.api_key": {"provider": "openai", "key_name": "api_key", "description": "OpenAI API key (for Codex)"},
    "neo4j.password": {"provider": "neo4j", "key_name": "password", "description": "Neo4j password"},
    "slack.app_token": {"provider": "slack", "key_name": "app_token", "description": "Slack app token (xapp-...)"},
    "slack.bot_token": {"provider": "slack", "key_name": "bot_token", "description": "Slack bot token (xoxb-...)"},
}


def load_config() -> HarnessConfig:
    """Load bootstrap configuration.

    Only reads DEVHARNESS_STORAGE_DIR from the environment. All other
    config is loaded from the DB later via load_config_from_db().
    """
    overrides: dict[str, Any] = {}

    storage_dir = os.environ.get(STORAGE_DIR_ENV)
    if storage_dir:
        overrides["storage_dir"] = Path(storage_dir)

    return HarnessConfig(**overrides)


async def load_config_from_db(config: HarnessConfig, storage: Any) -> HarnessConfig:
    """Overlay DB settings onto the bootstrap config.

    Called after storage is initialized. Reads all settings from the DB
    and applies them to the config object.
    """
    updates: dict[str, Any] = {}

    for key, meta in SETTINGS_KEYS.items():
        value = await storage.get_setting(key)
        if value is not None:
            field = meta["field"]
            type_name = meta["type"]
            try:
                if type_name == "int":
                    updates[field] = int(value)
                elif type_name == "bool":
                    updates[field] = value.lower() in ("true", "1", "yes")
                elif type_name == "path":
                    updates[field] = Path(value)
                else:
                    updates[field] = value
            except (ValueError, TypeError):
                logger.warning("Invalid DB setting %s=%s, using default", key, value)

    # Load API keys from credentials table
    for cred_key, cred_meta in CREDENTIAL_KEYS.items():
        if cred_key == "anthropic.api_key":
            value = await storage.load_credential(None, cred_meta["provider"], cred_meta["key_name"])
            if value:
                os.environ.setdefault("ANTHROPIC_API_KEY", value)
        elif cred_key == "openai.api_key":
            value = await storage.load_credential(None, cred_meta["provider"], cred_meta["key_name"])
            if value:
                os.environ.setdefault("OPENAI_API_KEY", value)

    if updates:
        config = config.model_copy(update=updates)

    return config


async def save_config_to_db(key: str, value: str, storage: Any) -> None:
    """Save a single config setting to the DB.

    Used by `harness config set`, the UI, and the agent itself.
    """
    if key in SETTINGS_KEYS:
        await storage.set_setting(key, value)
    elif key in CREDENTIAL_KEYS:
        meta = CREDENTIAL_KEYS[key]
        await storage.save_credential(None, meta["provider"], meta["key_name"], value)
    else:
        raise ValueError(
            f"Unknown config key: {key}. "
            f"Valid keys: {', '.join(sorted(list(SETTINGS_KEYS.keys()) + list(CREDENTIAL_KEYS.keys())))}"
        )


def list_config_keys() -> list[dict[str, str]]:
    """Return all configurable keys with descriptions.

    Used by `harness config list` and the UI settings page.
    """
    keys = []
    for key, meta in sorted(SETTINGS_KEYS.items()):
        keys.append({"key": key, "type": meta["type"], "description": meta["description"]})
    for key, meta in sorted(CREDENTIAL_KEYS.items()):
        keys.append({"key": key, "type": "secret", "description": meta["description"]})
    return keys
