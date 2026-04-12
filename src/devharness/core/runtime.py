"""Runtime orchestrator -- the heart of the harness.

Manages the session-level agent loop:
1. CONTEXT:     Build tiered context
2. PLAN:        Decompose task (optional)
3. HOOKS:       Run pre_turn hooks
4. DELEGATE:    Send task to agent backend
5. OBSERVE:     Stream agent events + run observer pipeline
6. HOOKS:       Run post_tool_call hooks
7. VERIFY:      Run verification pipeline
8. FEEDBACK:    Generate ObservationSummary
9. REPAIR:      Re-delegate if failures (max N)
10. HOOKS:      Run post_turn hooks
11. CHECKPOINT: Save state
12. SUMMARIZE:  Generate turn summary
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncIterator

from devharness.core.errors import (
    AgentNotFoundError,
    ApprovalDeniedError,
    ThreadAlreadyRunningError,
    ThreadNotFoundError,
)
from devharness.core.event_bus import EventBus
from devharness.core.models import (
    AgentConstraints,
    AgentContext,
    AgentEvent,
    ApprovalMode,
    ApprovalRequest,
    ApprovalStatus,
    Artifact,
    ArtifactKind,
    Checkpoint,
    Event,
    EventKind,
    HookEvent,
    Thread,
    ThreadConfig,
    ThreadStatus,
    Turn,
)

if TYPE_CHECKING:
    from devharness.agents.base import AgentBackend
    from devharness.artifacts.manager import ArtifactManager
    from devharness.context.architecture import ContextArchitecture
    from devharness.hooks.engine import HookEngine
    from devharness.observers.pipeline import ObserverPipeline
    from devharness.observers.summary import build_observation_summary, format_summary_for_agent
    from devharness.policies.engine import PolicyEngine
    from devharness.skills.registry import SkillRegistry
    from devharness.storage.base import StorageBackend
    from devharness.verification.pipeline import VerificationPipeline

logger = logging.getLogger(__name__)


class Runtime:
    """Orchestrates the agent loop at the session level."""

    def __init__(
        self,
        event_bus: EventBus,
        storage: "StorageBackend",
        agent_backends: dict[str, "AgentBackend"],
        context_arch: "ContextArchitecture",
        hook_engine: "HookEngine",
        policy_engine: "PolicyEngine",
        observer_pipeline: "ObserverPipeline",
        verification_pipeline: "VerificationPipeline",
        skill_registry: "SkillRegistry",
        artifact_manager: "ArtifactManager",
    ) -> None:
        self._event_bus = event_bus
        self._storage = storage
        self._agents = agent_backends
        self._context = context_arch
        self._hooks = hook_engine
        self._policy = policy_engine
        self._observers = observer_pipeline
        self._verification = verification_pipeline
        self._skills = skill_registry
        self._artifacts = artifact_manager

    # --- Public API ---

    async def create_thread(self, config: ThreadConfig | None = None) -> Thread:
        """Create a new thread."""
        thread = Thread(
            config=config or ThreadConfig(),
            project_id=config.project_id if config else None,
        )
        await self._storage.save_thread(thread)
        await self._emit(EventKind.THREAD_CREATED, thread.id)
        return thread

    async def run_turn(
        self, thread_id: str, user_input: str, max_repair_attempts: int = 2
    ) -> Turn:
        """Execute one full turn of the harness loop."""
        thread = await self._storage.load_thread(thread_id)

        if thread.status == ThreadStatus.RUNNING:
            raise ThreadAlreadyRunningError(f"Thread {thread_id} is already running")

        # Create turn
        turn = Turn(thread_id=thread.id, user_input=user_input)
        thread.turns.append(turn)
        thread.current_turn_id = turn.id
        thread.status = ThreadStatus.RUNNING
        thread.updated_at = datetime.now(timezone.utc)

        await self._emit(EventKind.TURN_START, thread.id, turn.id)
        await self._storage.save_thread(thread)

        # 1. HOOKS: pre_turn
        hook_result = await self._hooks.run_hooks(
            HookEvent.PRE_TURN, {"thread_id": thread.id, "user_input": user_input}
        )
        if hook_result and hook_result.exit_code == 2:
            user_input += f"\n\n[Hook feedback]\n{hook_result.stdout}"

        # 2. CONTEXT: build tiered context
        agent_context = self._context.build_context(thread, user_input)

        # 3. DELEGATE: run agent
        backend = self._get_agent_backend(thread.config.agent_backend)
        constraints = AgentConstraints(
            approval_mode=thread.config.approval_mode,
            allowed_tools=thread.config.allowed_tools,
            denied_tools=thread.config.denied_tools,
            workspace_root=thread.config.workspace_root,
            max_tool_calls=thread.config.max_tool_calls_per_turn,
        )

        await self._emit(EventKind.AGENT_STARTED, thread.id, turn.id)

        try:
            agent_response = ""
            async for event in backend.run_task(
                prompt=user_input,
                context=agent_context,
                tools=[],  # tools are managed by the agent backend directly
                constraints=constraints,
            ):
                await self._emit(
                    EventKind.AGENT_OUTPUT,
                    thread.id,
                    turn.id,
                    data=event.model_dump(mode="json"),
                )
                if event.type == "text":
                    agent_response += event.data.get("text", "")

            turn.assistant_response = agent_response
            await self._emit(EventKind.AGENT_COMPLETED, thread.id, turn.id)

        except Exception as e:
            turn.error = str(e)
            await self._emit(
                EventKind.AGENT_ERROR,
                thread.id,
                turn.id,
                data={"error": str(e)},
            )
            thread.status = ThreadStatus.FAILED
            turn.ended_at = datetime.now(timezone.utc)
            await self._storage.save_thread(thread)
            await self._emit(EventKind.TURN_END, thread.id, turn.id)
            return turn

        # 4. OBSERVE: run observer pipeline
        observations = await self._observers.observe_all(thread, turn)

        # 5. VERIFY: run verification (if enabled)
        if thread.config.verification_enabled:
            report = await self._verification.run(thread, turn)
            turn.verification = report

            if not report.all_passed and max_repair_attempts > 0:
                # Inject verification failures and re-run
                logger.info(
                    "Verification failed, attempting repair (%d attempts left)",
                    max_repair_attempts,
                )
                repair_input = (
                    f"Verification failed. Fix the following issues:\n"
                    + "\n".join(
                        f"- {r.verifier_name}: {r.message}"
                        for r in report.results
                        if not r.passed
                    )
                )
                # Recursive repair turn
                turn.ended_at = datetime.now(timezone.utc)
                await self._storage.save_thread(thread)
                return await self.run_turn(
                    thread_id, repair_input, max_repair_attempts - 1
                )

        # 6. HOOKS: post_turn
        await self._hooks.run_hooks(
            HookEvent.POST_TURN,
            {"thread_id": thread.id, "turn_id": turn.id},
        )

        # 7. CHECKPOINT
        turn.ended_at = datetime.now(timezone.utc)
        thread.status = ThreadStatus.COMPLETED
        thread.updated_at = datetime.now(timezone.utc)
        await self._storage.save_thread(thread)

        checkpoint = Checkpoint(
            thread_id=thread.id,
            thread_snapshot=thread,
        )
        await self._storage.save_checkpoint(checkpoint)
        await self._emit(EventKind.CHECKPOINT_SAVED, thread.id, turn.id)
        await self._emit(EventKind.TURN_END, thread.id, turn.id)

        return turn

    async def resume_thread(self, thread_id: str) -> Thread:
        """Resume a paused thread after approval resolution."""
        thread = await self._storage.load_thread(thread_id)
        if thread.status != ThreadStatus.PAUSED:
            raise ThreadAlreadyRunningError(
                f"Thread {thread_id} is not paused (status: {thread.status})"
            )

        thread.status = ThreadStatus.RUNNING
        thread.pending_approval = None
        await self._storage.save_thread(thread)
        await self._emit(EventKind.THREAD_RESUMED, thread.id)
        return thread

    async def resolve_approval(
        self,
        thread_id: str,
        approval_id: str,
        approved: bool,
        reason: str = "",
    ) -> None:
        """Resolve a pending approval request."""
        thread = await self._storage.load_thread(thread_id)

        if not thread.pending_approval or thread.pending_approval.id != approval_id:
            raise ValueError(f"No matching pending approval: {approval_id}")

        thread.pending_approval.status = (
            ApprovalStatus.USER_APPROVED if approved else ApprovalStatus.DENIED
        )
        thread.pending_approval.decided_by = "user"
        thread.pending_approval.decided_at = datetime.now(timezone.utc)
        if not approved:
            thread.pending_approval.denial_reason = reason

        await self._emit(
            EventKind.APPROVAL_RESOLVED,
            thread.id,
            data={
                "approval_id": approval_id,
                "approved": approved,
                "reason": reason,
            },
        )
        await self._storage.save_thread(thread)

    async def cancel_thread(self, thread_id: str) -> None:
        """Cancel a running or paused thread."""
        thread = await self._storage.load_thread(thread_id)
        thread.status = ThreadStatus.CANCELLED
        thread.updated_at = datetime.now(timezone.utc)
        await self._storage.save_thread(thread)
        await self._emit(EventKind.THREAD_CANCELLED, thread.id)

    async def replay_thread(self, thread_id: str) -> AsyncIterator[Event]:
        """Yield events from persisted state for replay."""
        events = await self._storage.load_events(thread_id)
        for event in events:
            yield event

    async def get_thread(self, thread_id: str) -> Thread:
        return await self._storage.load_thread(thread_id)

    async def list_threads(self, project_id: str | None = None) -> list[Thread]:
        return await self._storage.list_threads(project_id)

    # --- Internal helpers ---

    def _get_agent_backend(self, name: str) -> "AgentBackend":
        backend = self._agents.get(name)
        if backend is None:
            raise AgentNotFoundError(
                f"Agent backend '{name}' not registered. "
                f"Available: {list(self._agents.keys())}"
            )
        return backend

    async def _emit(
        self,
        kind: EventKind,
        thread_id: str,
        turn_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        event = Event(
            thread_id=thread_id,
            turn_id=turn_id,
            kind=kind,
            data=data or {},
        )
        await self._event_bus.emit(event)
