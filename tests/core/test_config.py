"""Tests for devharness.core.config.

Config is DB-first. The only env var is DEVHARNESS_STORAGE_DIR.
Everything else is stored in the DB and loaded via load_config_from_db().
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from devharness.core.config import (
    CREDENTIAL_KEYS,
    SETTINGS_KEYS,
    HarnessConfig,
    list_config_keys,
    load_config,
    load_config_from_db,
    save_config_to_db,
)
from devharness.core.models import ApprovalMode


# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------


class TestDefaultConfig:
    def test_default_storage_dir(self) -> None:
        cfg = HarnessConfig()
        assert cfg.storage_dir == Path(".devharness")

    def test_default_server(self) -> None:
        cfg = HarnessConfig()
        assert cfg.server_host == "127.0.0.1"
        assert cfg.server_port == 8390

    def test_default_approval_mode(self) -> None:
        cfg = HarnessConfig()
        assert cfg.default_approval_mode == ApprovalMode.AUTO_APPROVE_SAFE

    def test_default_agent_backend(self) -> None:
        cfg = HarnessConfig()
        assert cfg.default_agent_backend == "claude-code"

    def test_default_log_level(self) -> None:
        cfg = HarnessConfig()
        assert cfg.log_level == "INFO"

    def test_get_db_path_default(self) -> None:
        cfg = HarnessConfig()
        assert cfg.get_db_path() == Path(".devharness") / "harness.db"

    def test_get_db_path_explicit(self) -> None:
        cfg = HarnessConfig(db_path=Path("/tmp/custom.db"))
        assert cfg.get_db_path() == Path("/tmp/custom.db")

    def test_load_config_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cfg = load_config()
        assert isinstance(cfg, HarnessConfig)
        assert cfg.server_host == "127.0.0.1"


# ---------------------------------------------------------------------------
# Bootstrap env var (the only one)
# ---------------------------------------------------------------------------


class TestBootstrapEnvVar:
    def test_storage_dir_override(self) -> None:
        with patch.dict(os.environ, {"DEVHARNESS_STORAGE_DIR": "/custom/path"}):
            cfg = load_config()
        assert cfg.storage_dir == Path("/custom/path")

    def test_no_other_env_vars_read(self) -> None:
        """Only DEVHARNESS_STORAGE_DIR is read. Other env vars are ignored."""
        env = {
            "DEVHARNESS_HOST": "0.0.0.0",
            "DEVHARNESS_PORT": "9999",
            "ANTHROPIC_API_KEY": "sk-test",
        }
        with patch.dict(os.environ, env):
            cfg = load_config()
        # These should NOT be overridden by env vars
        assert cfg.server_host == "127.0.0.1"
        assert cfg.server_port == 8390


# ---------------------------------------------------------------------------
# DB-first config loading
# ---------------------------------------------------------------------------


class TestDbConfig:
    @pytest.mark.asyncio
    async def test_load_config_from_db(self, tmp_storage) -> None:
        """Settings stored in DB override defaults."""
        storage = tmp_storage
        await storage.set_setting("server.port", "9999")
        await storage.set_setting("log.level", "DEBUG")

        cfg = HarnessConfig()
        cfg = await load_config_from_db(cfg, storage)

        assert cfg.server_port == 9999
        assert cfg.log_level == "DEBUG"

    @pytest.mark.asyncio
    async def test_load_config_from_db_empty(self, tmp_storage) -> None:
        """No DB settings means defaults are kept."""
        cfg = HarnessConfig()
        cfg = await load_config_from_db(cfg, tmp_storage)

        assert cfg.server_port == 8390
        assert cfg.log_level == "INFO"

    @pytest.mark.asyncio
    async def test_save_and_load_setting(self, tmp_storage) -> None:
        """Settings can be saved and loaded round-trip."""
        await save_config_to_db("default.agent_backend", "codex", tmp_storage)

        cfg = HarnessConfig()
        cfg = await load_config_from_db(cfg, tmp_storage)
        assert cfg.default_agent_backend == "codex"

    @pytest.mark.asyncio
    async def test_save_credential(self, tmp_storage) -> None:
        """Credentials are stored via save_config_to_db."""
        await save_config_to_db("anthropic.api_key", "sk-test-123", tmp_storage)

        cred = await tmp_storage.load_credential(None, "anthropic", "api_key")
        assert cred == "sk-test-123"

    @pytest.mark.asyncio
    async def test_save_invalid_key_raises(self, tmp_storage) -> None:
        """Unknown config keys raise ValueError."""
        with pytest.raises(ValueError, match="Unknown config key"):
            await save_config_to_db("nonexistent.key", "value", tmp_storage)

    @pytest.mark.asyncio
    async def test_bool_setting(self, tmp_storage) -> None:
        """Bool settings are parsed correctly."""
        await save_config_to_db("neo4j.enabled", "true", tmp_storage)

        cfg = HarnessConfig()
        cfg = await load_config_from_db(cfg, tmp_storage)
        assert cfg.neo4j_enabled is True


# ---------------------------------------------------------------------------
# Config key registry
# ---------------------------------------------------------------------------


class TestConfigKeys:
    def test_list_config_keys_not_empty(self) -> None:
        keys = list_config_keys()
        assert len(keys) > 0

    def test_list_config_keys_has_settings_and_credentials(self) -> None:
        keys = list_config_keys()
        key_names = {k["key"] for k in keys}
        assert "server.port" in key_names
        assert "anthropic.api_key" in key_names

    def test_all_settings_keys_have_field(self) -> None:
        for key, meta in SETTINGS_KEYS.items():
            assert "field" in meta, f"Settings key {key} missing 'field'"
            assert "type" in meta, f"Settings key {key} missing 'type'"

    def test_all_credential_keys_have_provider(self) -> None:
        for key, meta in CREDENTIAL_KEYS.items():
            assert "provider" in meta, f"Credential key {key} missing 'provider'"
            assert "key_name" in meta, f"Credential key {key} missing 'key_name'"
