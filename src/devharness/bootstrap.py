"""Bootstrap the harness runtime.

Wires together all components: storage, event bus, agent backends, tools,
policies, skills, verification, observers, hooks, artifacts, and the runtime.

Config is DB-first: only DEVHARNESS_STORAGE_DIR env var is needed to find
the database. Everything else is loaded from the DB settings table.
"""

from __future__ import annotations

import logging

from devharness.agents.claude_code import ClaudeCodeBackend
from devharness.agents.codex import CodexBackend
from devharness.artifacts.manager import ArtifactManager
from devharness.context.architecture import ContextArchitecture
from devharness.core.config import HarnessConfig, load_config_from_db
from devharness.core.event_bus import EventBus
from devharness.core.runtime import Runtime
from devharness.enforcement.engine import EnforcementEngine
from devharness.hooks.engine import HookEngine
from devharness.hooks.registry import HookRegistry
from devharness.observers.pipeline import ObserverPipeline
from devharness.policies.engine import PolicyEngine
from devharness.skills.registry import SkillRegistry
from devharness.storage.sqlite import SqliteStorage
from devharness.telemetry.logger import setup_logging
from devharness.verification.pipeline import VerificationPipeline

logger = logging.getLogger(__name__)


async def bootstrap(config: HarnessConfig) -> Runtime:
    """Create and wire all harness components. Returns a ready-to-use Runtime.

    1. Initialize SQLite storage
    2. Load config from DB (overlay onto bootstrap config)
    3. Wire all components
    """
    setup_logging(config.log_level)
    logger.info("Bootstrapping harness...")

    # 1. Storage -- must come first so we can load config from DB
    storage = SqliteStorage(config.get_db_path())
    await storage.initialize()

    # 2. Load config from DB (overrides defaults with stored settings)
    config = await load_config_from_db(config, storage)
    setup_logging(config.log_level)  # re-apply in case log level changed

    # 3. Event bus
    event_bus = EventBus()

    # Wire event bus -> storage (persist all events)
    event_bus.subscribe(None, storage.save_event)

    # Agent backends
    agent_backends = {
        "claude-code": ClaudeCodeBackend(),
        "codex": CodexBackend(),
    }

    # Context architecture
    context_arch = ContextArchitecture()

    # Hook system
    hook_registry = HookRegistry()
    hook_engine = HookEngine()

    # Policy engine
    policy_engine = PolicyEngine()

    # Observer pipeline
    observer_pipeline = ObserverPipeline(event_bus=event_bus)

    # Verification pipeline
    verification_pipeline = VerificationPipeline()

    # Skill registry
    skill_registry = SkillRegistry()

    # Artifact manager
    artifact_manager = ArtifactManager(event_bus=event_bus)

    # Runtime
    runtime = Runtime(
        event_bus=event_bus,
        storage=storage,
        agent_backends=agent_backends,
        context_arch=context_arch,
        hook_engine=hook_engine,
        policy_engine=policy_engine,
        observer_pipeline=observer_pipeline,
        verification_pipeline=verification_pipeline,
        skill_registry=skill_registry,
        artifact_manager=artifact_manager,
    )

    logger.info("Harness bootstrapped successfully")
    return runtime


async def shutdown(runtime: Runtime) -> None:
    """Clean up resources."""
    logger.info("Shutting down harness...")
    await runtime._observers.stop_all()
    await runtime._storage.close()
    logger.info("Harness shut down")
