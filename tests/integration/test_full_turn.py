"""Integration test: bootstrap a runtime, create a thread, run a turn."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from devharness.agents.base import AgentBackend
from devharness.artifacts.manager import ArtifactManager
from devharness.context.architecture import ContextArchitecture
from devharness.core.event_bus import EventBus
from devharness.core.models import (
    AgentConstraints,
    AgentContext,
    AgentEvent,
    Event,
    EventKind,
    HookResult,
    Thread,
    ThreadConfig,
    ThreadStatus,
    Turn,
    VerificationReport,
    VerificationResult,
)
from devharness.core.runtime import Runtime
from devharness.hooks.engine import HookEngine
from devharness.observers.pipeline import ObserverPipeline
from devharness.policies.engine import PolicyEngine
from devharness.skills.registry import SkillRegistry
from devharness.storage.sqlite import SqliteStorage
from devharness.verification.pipeline import VerificationPipeline


# ---------------------------------------------------------------------------
# Mock agent backend
# ---------------------------------------------------------------------------


class MockAgentBackend(AgentBackend):
    """Agent backend that yields a single text event and completes."""

    def __init__(self, response_text: str = "Done.") -> None:
        self._response_text = response_text

    async def run_task(
        self,
        prompt: str,
        context: AgentContext,
        tools: list[str],
        constraints: AgentConstraints,
    ) -> AsyncIterator[AgentEvent]:
        yield AgentEvent(type="text", data={"text": self._response_text})

    async def cancel(self) -> None:
        pass

    async def health_check(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


async def test_full_turn_lifecycle(tmp_path: Path) -> None:
    """Bootstrap a runtime, create a thread, run a turn, verify outcomes."""

    # --- Setup storage ---
    db_path = tmp_path / "integration.db"
    storage = SqliteStorage(db_path)
    await storage.initialize()

    try:
        # --- Setup components ---
        event_bus = EventBus()
        mock_backend = MockAgentBackend(response_text="I completed the task.")

        # Create mock hook engine that accepts 2-arg calls (runtime passes 2 args)
        hook_engine = AsyncMock(spec=HookEngine)
        hook_engine.run_hooks = AsyncMock(return_value=None)

        # Context architecture with defaults
        context_arch = ContextArchitecture()

        # Policy engine with defaults
        policy_engine = PolicyEngine()

        # Observer pipeline (no observers)
        observer_pipeline = ObserverPipeline(event_bus=event_bus)

        # Verification pipeline that always passes
        verification_pipeline = AsyncMock(spec=VerificationPipeline)
        verification_pipeline.run = AsyncMock(
            return_value=VerificationReport(
                thread_id="",
                turn_id="",
                all_passed=True,
                results=[
                    VerificationResult(
                        verifier_name="mock", passed=True, message="OK"
                    )
                ],
            )
        )

        # Skill registry (empty)
        skill_registry = SkillRegistry()

        # Artifact manager
        artifact_manager = ArtifactManager(event_bus)

        # --- Build runtime ---
        runtime = Runtime(
            event_bus=event_bus,
            storage=storage,
            agent_backends={"claude-code": mock_backend},
            context_arch=context_arch,
            hook_engine=hook_engine,
            policy_engine=policy_engine,
            observer_pipeline=observer_pipeline,
            verification_pipeline=verification_pipeline,
            skill_registry=skill_registry,
            artifact_manager=artifact_manager,
        )

        # --- Track events ---
        emitted_events: list[Event] = []

        async def track_event(event: Event) -> None:
            emitted_events.append(event)

        event_bus.subscribe(None, track_event)

        # --- Create thread ---
        thread = await runtime.create_thread(
            ThreadConfig(agent_backend="claude-code")
        )
        assert isinstance(thread, Thread)
        assert thread.status == ThreadStatus.PENDING

        # --- Run a turn ---
        turn = await runtime.run_turn(thread.id, "Build the feature")
        assert isinstance(turn, Turn)
        assert turn.assistant_response == "I completed the task."

        # --- Verify events were emitted ---
        event_kinds = [e.kind for e in emitted_events]
        assert EventKind.THREAD_CREATED in event_kinds
        assert EventKind.TURN_START in event_kinds
        assert EventKind.AGENT_STARTED in event_kinds
        assert EventKind.AGENT_COMPLETED in event_kinds
        assert EventKind.TURN_END in event_kinds

        # --- Verify events stored in event bus log ---
        thread_events = event_bus.events_for_thread(thread.id)
        assert len(thread_events) >= 5

        # --- Verify thread status is completed ---
        final_thread = await runtime.get_thread(thread.id)
        assert final_thread.status == ThreadStatus.COMPLETED
        assert len(final_thread.turns) == 1
        assert final_thread.turns[0].assistant_response == "I completed the task."

    finally:
        await storage.close()


async def test_turn_with_agent_error(tmp_path: Path) -> None:
    """Verify that an agent error results in FAILED thread status."""

    db_path = tmp_path / "error_test.db"
    storage = SqliteStorage(db_path)
    await storage.initialize()

    try:
        event_bus = EventBus()

        class FailingBackend(AgentBackend):
            async def run_task(self, prompt, context, tools, constraints):
                raise RuntimeError("Agent crashed")
                # Make this an async generator for the async for loop
                yield  # noqa: unreachable

            async def cancel(self) -> None:
                pass

            async def health_check(self) -> bool:
                return False

        hook_engine = AsyncMock(spec=HookEngine)
        hook_engine.run_hooks = AsyncMock(return_value=None)

        runtime = Runtime(
            event_bus=event_bus,
            storage=storage,
            agent_backends={"claude-code": FailingBackend()},
            context_arch=ContextArchitecture(),
            hook_engine=hook_engine,
            policy_engine=PolicyEngine(),
            observer_pipeline=ObserverPipeline(event_bus=event_bus),
            verification_pipeline=AsyncMock(spec=VerificationPipeline),
            skill_registry=SkillRegistry(),
            artifact_manager=ArtifactManager(event_bus),
        )

        thread = await runtime.create_thread()
        turn = await runtime.run_turn(thread.id, "do something")

        assert turn.error is not None
        assert "crashed" in turn.error.lower()

        failed_thread = await runtime.get_thread(thread.id)
        assert failed_thread.status == ThreadStatus.FAILED

    finally:
        await storage.close()
