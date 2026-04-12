"""All domain models for the harness.

Every other module imports from here. Models are in a single file to prevent
circular imports -- they reference each other heavily (Thread contains Turns,
Turns contain ToolCalls, etc.).

All models use Pydantic v2 for validation, serialization, and JSON Schema generation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ThreadStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"  # waiting for approval
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ApprovalMode(StrEnum):
    FULL_TRUST = "full_trust"
    AUTO_APPROVE_SAFE = "auto_approve_safe"
    APPROVAL_REQUIRED = "approval_required"
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    AUTO_APPROVED = "auto_approved"
    USER_APPROVED = "user_approved"
    DENIED = "denied"


class ToolCategory(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class EventKind(StrEnum):
    # Thread lifecycle
    THREAD_CREATED = "thread.created"
    THREAD_STARTED = "thread.started"
    THREAD_PAUSED = "thread.paused"
    THREAD_RESUMED = "thread.resumed"
    THREAD_COMPLETED = "thread.completed"
    THREAD_FAILED = "thread.failed"
    THREAD_CANCELLED = "thread.cancelled"

    # Turn lifecycle
    TURN_START = "turn.start"
    TURN_END = "turn.end"

    # Agent
    AGENT_STARTED = "agent.started"
    AGENT_OUTPUT = "agent.output"
    AGENT_COMPLETED = "agent.completed"
    AGENT_ERROR = "agent.error"

    # Tool calls
    TOOL_CALL_START = "tool_call.start"
    TOOL_CALL_END = "tool_call.end"

    # Approvals
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"

    # Verification
    VERIFICATION_START = "verification.start"
    VERIFICATION_END = "verification.end"

    # Observations
    OBSERVATION = "observation"
    BROWSER_TEST_PASSED = "browser_test.passed"
    BROWSER_TEST_FAILED = "browser_test.failed"

    # Hooks
    HOOK_START = "hook.start"
    HOOK_END = "hook.end"
    HOOK_REENGAGE = "hook.reengage"

    # Artifacts
    ARTIFACT_CREATED = "artifact.created"

    # Checkpoints
    CHECKPOINT_SAVED = "checkpoint.saved"

    # Errors
    ERROR = "error"


class ArtifactKind(StrEnum):
    PATCH = "patch"
    PLAN = "plan"
    SUMMARY = "summary"
    REPORT = "report"
    TRANSCRIPT = "transcript"
    SCREENSHOT = "screenshot"
    TEST_REPORT = "test_report"
    LOG = "log"


class ObservationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class HookEvent(StrEnum):
    PRE_TURN = "pre_turn"
    POST_TURN = "post_turn"
    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"
    PRE_COMMIT = "pre_commit"
    POST_COMMIT = "post_commit"
    ON_ERROR = "on_error"
    ON_IDLE = "on_idle"


class ContextTier(StrEnum):
    HOT = "hot"      # always loaded
    WARM = "warm"    # task-activated
    COLD = "cold"    # on-demand retrieval


class TaskStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


# ---------------------------------------------------------------------------
# Core domain models
# ---------------------------------------------------------------------------


class Project(BaseModel):
    """A project workspace managed by the harness."""

    id: str = Field(default_factory=_new_id)
    name: str
    workspace_root: str
    agent_backend: str = "claude-code"
    default_approval_mode: ApprovalMode = ApprovalMode.AUTO_APPROVE_SAFE
    skills: list[str] = Field(default_factory=list)
    observer_config: dict[str, Any] = Field(default_factory=dict)
    context_files: list[str] = Field(default_factory=list)
    browser_test_flows: list[str] = Field(default_factory=list)
    memory_backend: str = "none"  # "neo4j" | "obsidian" | "none"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class ThreadConfig(BaseModel):
    """Per-thread settings."""

    project_id: str | None = None
    agent_backend: str = "claude-code"
    approval_mode: ApprovalMode = ApprovalMode.AUTO_APPROVE_SAFE
    workspace_root: str = "."
    allowed_tools: list[str] | None = None  # None = all tools
    denied_tools: list[str] | None = None
    skills: list[str] = Field(default_factory=list)
    max_turns: int = 50
    max_tool_calls_per_turn: int = 100
    verification_enabled: bool = True
    context_window: int = 200_000
    system_prompt_override: str | None = None


class ToolResult(BaseModel):
    """Structured output from a tool execution."""

    output: str
    is_error: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    truncated: bool = False


class ToolCall(BaseModel):
    """Record of a single tool invocation."""

    id: str = Field(default_factory=_new_id)
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: float | None = None
    result: ToolResult | None = None
    error: str | None = None


class ApprovalRequest(BaseModel):
    """A pausable approval gate for a tool call."""

    id: str = Field(default_factory=_new_id)
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    category: ToolCategory = ToolCategory.EXECUTE
    reason: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_by: str | None = None  # "policy:<mode>" or "user" or "slack"
    decided_at: datetime | None = None
    denial_reason: str | None = None


class Step(BaseModel):
    """A single step in a plan."""

    id: str = Field(default_factory=_new_id)
    sequence: int = 0
    description: str
    status: StepStatus = StepStatus.PENDING
    tool_calls: list[str] = Field(default_factory=list)  # ToolCall IDs
    result_summary: str | None = None
    error: str | None = None


class Plan(BaseModel):
    """A structured plan with trackable steps."""

    id: str = Field(default_factory=_new_id)
    goal: str
    steps: list[Step] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    current_step_index: int = 0


class Event(BaseModel):
    """Structured log entry emitted by the harness."""

    id: str = Field(default_factory=_new_id)
    thread_id: str
    turn_id: str | None = None
    kind: EventKind
    timestamp: datetime = Field(default_factory=_now)
    data: dict[str, Any] = Field(default_factory=dict)


class Artifact(BaseModel):
    """A generated output (patch, screenshot, report, etc.)."""

    id: str = Field(default_factory=_new_id)
    thread_id: str
    turn_id: str | None = None
    kind: ArtifactKind
    name: str
    content: str = ""
    file_path: str | None = None  # for binary artifacts stored on disk
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


class VerificationResult(BaseModel):
    """Result from a single verifier."""

    verifier_name: str
    passed: bool
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0


class VerificationReport(BaseModel):
    """Aggregate results from the verification pipeline."""

    id: str = Field(default_factory=_new_id)
    thread_id: str
    turn_id: str
    results: list[VerificationResult] = Field(default_factory=list)
    all_passed: bool = False
    created_at: datetime = Field(default_factory=_now)


class PolicyDecision(BaseModel):
    """Result of evaluating a tool call against the policy engine."""

    allowed: bool
    mode: ApprovalMode
    reason: str
    requires_user_approval: bool = False


class Turn(BaseModel):
    """One cycle of agent work within a thread."""

    id: str = Field(default_factory=_new_id)
    thread_id: str
    user_input: str
    plan: Plan | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)  # Event IDs
    verification: VerificationReport | None = None
    artifacts: list[str] = Field(default_factory=list)  # Artifact IDs
    assistant_response: str | None = None
    started_at: datetime = Field(default_factory=_now)
    ended_at: datetime | None = None
    error: str | None = None


class Thread(BaseModel):
    """Session container -- the top-level unit of work."""

    id: str = Field(default_factory=_new_id)
    project_id: str | None = None
    status: ThreadStatus = ThreadStatus.PENDING
    config: ThreadConfig = Field(default_factory=ThreadConfig)
    turns: list[Turn] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    current_turn_id: str | None = None
    pending_approval: ApprovalRequest | None = None


class Checkpoint(BaseModel):
    """Serializable snapshot of a thread for persistence/replay."""

    thread_id: str
    thread_snapshot: Thread
    events: list[Event] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    saved_at: datetime = Field(default_factory=_now)


class SkillManifest(BaseModel):
    """Metadata for a skill pack."""

    name: str
    version: str = "0.1.0"
    description: str = ""
    system_prompt: str = ""
    tools: list[str] = Field(default_factory=list)
    verifiers: list[str] = Field(default_factory=list)
    hooks: dict[str, Any] = Field(default_factory=dict)
    context_files: list[str] = Field(default_factory=list)
    config_schema: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Observation models (from observers)
# ---------------------------------------------------------------------------


class Observation(BaseModel):
    """A structured observation from an observer."""

    id: str = Field(default_factory=_new_id)
    observer_name: str
    thread_id: str
    turn_id: str | None = None
    severity: ObservationSeverity = ObservationSeverity.INFO
    title: str
    details: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_now)
    source_file: str | None = None
    source_line: int | None = None


class TestFailure(BaseModel):
    """Detail of a single test failure."""

    test_name: str
    file_path: str = ""
    line_number: int | None = None
    assertion_message: str = ""
    stack_trace: str = ""


class TestSummary(BaseModel):
    """Aggregate test runner results."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    errored: int = 0
    skipped: int = 0
    failures: list[TestFailure] = Field(default_factory=list)
    coverage_pct: float | None = None
    coverage_diff: float | None = None


class EndpointStatus(BaseModel):
    """Health status of a single HTTP endpoint."""

    url: str
    status_code: int | None = None
    response_time_ms: float | None = None
    is_healthy: bool = False
    error: str | None = None


class EndpointSummary(BaseModel):
    """Aggregate endpoint health."""

    endpoints: list[EndpointStatus] = Field(default_factory=list)
    healthy_count: int = 0
    unhealthy_count: int = 0


class ObservationSummary(BaseModel):
    """Summary of observations for a turn -- injected into agent context."""

    thread_id: str
    turn_id: str
    observations: list[Observation] = Field(default_factory=list)
    process_status: dict[str, str] = Field(default_factory=dict)
    test_summary: TestSummary | None = None
    endpoint_summary: EndpointSummary | None = None
    new_errors: int = 0
    new_warnings: int = 0
    generated_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Browser testing models
# ---------------------------------------------------------------------------


class BrowserTestStep(BaseModel):
    """A single step in a browser interaction flow."""

    action: str  # "click", "fill", "wait_for", "screenshot", "navigate"
    selector: str | None = None
    value: str | None = None
    name: str | None = None
    timeout: int = 5000


class BrowserAssertion(BaseModel):
    """An assertion in a browser test flow."""

    type: str  # "url_contains", "element_visible", "no_console_errors", "text_contains"
    value: str | None = None
    selector: str | None = None


class BrowserTestFlow(BaseModel):
    """A declarative browser interaction flow defined in YAML."""

    name: str
    url: str
    steps: list[BrowserTestStep] = Field(default_factory=list)
    assertions: list[BrowserAssertion] = Field(default_factory=list)
    viewport_width: int = 1280
    viewport_height: int = 720


class BrowserTestResult(BaseModel):
    """Result of executing a browser test flow."""

    flow_name: str
    passed: bool
    steps_completed: int = 0
    steps_total: int = 0
    failure_step: int | None = None
    failure_reason: str | None = None
    screenshots: list[str] = Field(default_factory=list)  # artifact IDs
    console_errors: list[str] = Field(default_factory=list)
    dom_snapshot: str | None = None
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# Hook models
# ---------------------------------------------------------------------------


class HookConfig(BaseModel):
    """Configuration for a lifecycle hook script."""

    name: str
    event: HookEvent
    script: str  # path to script or inline command
    enabled: bool = True
    on_tools: list[str] | None = None  # only trigger for these tools
    timeout: int = 60
    config: dict[str, Any] = Field(default_factory=dict)


class HookResult(BaseModel):
    """Result of executing a hook script."""

    hook_name: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# Context models
# ---------------------------------------------------------------------------


class ContextBudget(BaseModel):
    """Token budget tracking for tiered context loading."""

    max_tokens: int = 200_000
    tier1_tokens: int = 0
    tier2_tokens: int = 0
    tier3_tokens: int = 0
    utilization_target: float = 0.40  # 40% sweet spot

    @property
    def used_tokens(self) -> int:
        return self.tier1_tokens + self.tier2_tokens + self.tier3_tokens

    @property
    def remaining(self) -> int:
        return self.max_tokens - self.used_tokens

    @property
    def utilization(self) -> float:
        return self.used_tokens / self.max_tokens if self.max_tokens > 0 else 0.0


# ---------------------------------------------------------------------------
# Task DAG models
# ---------------------------------------------------------------------------


class TaskNode(BaseModel):
    """A node in a task dependency graph."""

    id: str = Field(default_factory=_new_id)
    content: str
    blocked_by: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: str | None = None  # sub-agent ID
    result: str | None = None
    error: str | None = None


class TaskDAG(BaseModel):
    """A dependency graph of tasks for parallel execution."""

    id: str = Field(default_factory=_new_id)
    goal: str
    nodes: list[TaskNode] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)

    def ready_nodes(self) -> list[TaskNode]:
        """Return nodes whose dependencies are all completed."""
        completed_ids = {n.id for n in self.nodes if n.status == TaskStatus.COMPLETED}
        return [
            n
            for n in self.nodes
            if n.status == TaskStatus.PENDING
            and all(dep in completed_ids for dep in n.blocked_by)
        ]

    @property
    def is_complete(self) -> bool:
        return all(
            n.status in (TaskStatus.COMPLETED, TaskStatus.FAILED) for n in self.nodes
        )


# ---------------------------------------------------------------------------
# Agent models
# ---------------------------------------------------------------------------


class AgentContext(BaseModel):
    """Context passed to an agent backend for a task."""

    system_prompt: str = ""
    instructions: list[str] = Field(default_factory=list)
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    observation_summary: str | None = None
    memory_context: str | None = None
    token_usage: ContextBudget = Field(default_factory=ContextBudget)


class AgentConstraints(BaseModel):
    """Constraints passed to an agent backend."""

    approval_mode: ApprovalMode = ApprovalMode.AUTO_APPROVE_SAFE
    allowed_tools: list[str] | None = None
    denied_tools: list[str] | None = None
    workspace_root: str = "."
    max_tool_calls: int = 100
    read_only: bool = False


class AgentEvent(BaseModel):
    """Structured event emitted by an agent backend during execution."""

    type: str  # "text", "tool_call", "tool_result", "error", "done"
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_now)


class SubAgentConfig(BaseModel):
    """Configuration for spawning a sub-agent with isolated context."""

    task: str
    model_override: str | None = None
    tools: list[str] = Field(default_factory=list)
    read_only: bool = False
    response_format: str = "summary"  # "summary" | "structured" | "citations"
    timeout: int = 300


class SubAgentResult(BaseModel):
    """Result from a sub-agent execution."""

    task: str
    response: str
    tool_calls_count: int = 0
    duration_ms: float = 0.0
    error: str | None = None


# ---------------------------------------------------------------------------
# Enforcement models
# ---------------------------------------------------------------------------


class EnforcementRule(BaseModel):
    """A mechanical enforcement rule with agent-readable correction prompts."""

    name: str
    check_command: str
    error_pattern: str = ""
    correction_prompt: str = ""
    architectural_layer: str | None = None
    enabled: bool = True


class EnforcementResult(BaseModel):
    """Result of running an enforcement rule."""

    rule_name: str
    passed: bool
    violations: list[str] = Field(default_factory=list)
    correction_prompt: str | None = None
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# Slack models
# ---------------------------------------------------------------------------


class SlackConfig(BaseModel):
    """Slack Socket Mode integration configuration."""

    enabled: bool = False
    app_token: str = ""
    bot_token: str = ""
    channel: str = "#dev-harness"
    approval_channel: str | None = None
    notify_on: list[str] = Field(
        default_factory=lambda: [
            "approval_requested",
            "turn_complete",
            "turn_failed",
            "browser_test_failed",
            "verification_failed",
        ]
    )


# ---------------------------------------------------------------------------
# Template models
# ---------------------------------------------------------------------------


class HarnessTemplate(BaseModel):
    """A pre-packaged harness configuration for a project type."""

    name: str
    description: str = ""
    default_skills: list[str] = Field(default_factory=list)
    default_hooks: list[HookConfig] = Field(default_factory=list)
    default_observers: dict[str, Any] = Field(default_factory=dict)
    default_enforcement: list[EnforcementRule] = Field(default_factory=list)
    context_files: dict[str, str] = Field(default_factory=dict)  # path -> content
    browser_flows: list[BrowserTestFlow] = Field(default_factory=list)
