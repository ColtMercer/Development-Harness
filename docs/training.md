# Development Harness -- Training Guide

This document is a comprehensive walkthrough of the Development Harness for engineers who want to understand, operate, and extend the system. Read it end to end once, then use it as a reference.

---

## 1. System Overview and Mental Model

The Development Harness is a control plane for autonomous coding agents. The core equation:

**Agent = Model + Harness**

The model (Claude, Codex, or any future LLM) provides reasoning and code generation. The harness provides everything else: lifecycle management, tool orchestration, context assembly, verification, observability, safety policies, and recovery.

Think of the harness as the operating system around the model. The model is a single process running inside it. The harness provides:

- **Feedforward controls** -- steer the agent *before* it acts: system prompts, skill instructions, architecture docs, linter rules, context files.
- **Feedback controls** -- detect issues *after* the agent acts: test runners, observers, verifiers, browser tests, enforcement checks.

These two control types form a closed loop. The agent acts, the harness evaluates, and if something is wrong the harness re-engages the agent with corrective context.

### Key Abstractions

| Concept | What it is |
|---------|-----------|
| **Thread** | A session container. The top-level unit of work. Contains turns, config, status. |
| **Turn** | One cycle of agent work within a thread. Contains the user prompt, tool calls, verification results, and the assistant response. |
| **Agent Backend** | A pluggable wrapper around a CLI agent (Claude Code, Codex). Spawns a subprocess, streams structured events. |
| **Tool** | An executable capability available to the agent. Categorized as read, write, or execute. |
| **Skill** | A composable pack: system prompt + tool set + verifiers. Loaded from a directory. |
| **Observer** | A monitor that watches some aspect of the application (process health, tests, logs, endpoints, browser state) and produces observations. |
| **Hook** | A script triggered at a lifecycle event (pre/post turn, pre/post tool call, pre/post commit, on error, on idle). |
| **Verification** | A post-turn check pipeline. Runs tests, linters, or custom verifiers. If verification fails, the harness re-delegates. |
| **Event** | A structured log entry emitted by the harness. Every significant action produces an event. |
| **Artifact** | A generated output: patch, plan, summary, screenshot, test report, etc. |
| **Policy** | Rules that determine whether a tool call is allowed, denied, or held for approval. |

---

## 2. Architectural Walkthrough

### Bootstrap

The entry point is `devharness.bootstrap.bootstrap()`. It wires all components together:

1. Initialize SQLite storage (create tables if needed).
2. Create the event bus (in-process async pub/sub).
3. Wire the event bus to storage (all events are persisted).
4. Create agent backends (ClaudeCodeBackend, CodexBackend).
5. Create the context architecture (tiered context builder).
6. Create the hook system (HookRegistry + HookEngine).
7. Create the policy engine (with default deny rules).
8. Create the observer pipeline.
9. Create the verification pipeline.
10. Create the skill registry.
11. Create the artifact manager.
12. Assemble the Runtime with all components injected.

The Runtime is the single object that the CLI and HTTP server interact with. Everything else is internal.

### The Event Bus

The event bus (`EventBus`) is the nervous system of the harness. Every significant action emits an `Event`. Subscribers filter by `EventKind` or subscribe to all events (wildcard `None`).

Subscribers run concurrently via `anyio` task groups. A failing subscriber logs the error but does not block other subscribers or the emitter. This means the event bus is fire-and-forget from the emitter's perspective.

By default, the storage backend subscribes to all events so every event is persisted to SQLite.

### Storage

All persistence is handled by the `StorageBackend` interface. The primary implementation is `SqliteStorage`. It stores:

- Projects
- Threads and turns
- Events
- Observations
- Artifacts (metadata in DB, large binaries on disk)
- Checkpoints (serialized thread snapshots)
- Credentials (encrypted)
- Settings (key-value)
- Memory event buffer (for Neo4j graceful degradation)

Configuration lives in the database, not in config files. Environment variables with the `DEVHARNESS_` prefix override database values.

---

## 3. Lifecycle of a Turn

When you run `harness run "fix the tests"`, the following sequence executes:

### Step 1: Thread Creation

A `Thread` object is created with a `ThreadConfig`. The config specifies the agent backend, approval mode, workspace root, allowed/denied tools, skills, max turns, max tool calls, verification settings, and context window size.

### Step 2: Pre-Turn Hooks

The hook engine runs all hooks registered for the `PRE_TURN` event. Each hook is a shell script. Exit code semantics:

- **0**: Success. Output is swallowed (silent -- no context pollution).
- **2**: Re-engage. Stdout is appended to the user input as `[Hook feedback]`.
- **Other**: Warning logged, execution continues.

If a pre-turn hook exits with code 2, its output is injected into the prompt. This lets hooks add dynamic context before the agent starts.

### Step 3: Context Assembly

The context architecture builds an `AgentContext` with three tiers:

- **Tier 1 (Hot)**: Always loaded. System prompt + project context files (CLAUDE.md, etc.). This is the project constitution.
- **Tier 2 (Warm)**: Task-activated. Current task instruction, skill prompts, observation summaries.
- **Tier 3 (Cold)**: On-demand. Never pre-loaded. Accessed via tools during execution.

The target is 40% context utilization. Tier 2 is trimmed if the budget is exceeded (oldest items dropped first).

### Step 4: Agent Delegation

The harness spawns the agent CLI as a subprocess:

- Claude Code: `claude --output-format stream-json --no-input -p "<prompt>"`
- Codex: `codex --prompt "<prompt>" --approval-mode <mode>`

The prompt includes the assembled context (system prompt, instructions, observations, memory context) wrapped in XML tags.

The harness streams the subprocess stdout line by line, parsing each JSON object into an `AgentEvent` (text, tool_call, tool_result, error, done).

### Step 5: Observation

After the agent completes, the observer pipeline runs all registered observers concurrently. Each observer returns a list of `Observation` objects. Observations are emitted as events on the bus.

Observers watch:
- Process health (is the dev server running?)
- Test results (did tests pass?)
- Lint output (new warnings?)
- Build status
- Log files (new errors?)
- Endpoint health (are HTTP endpoints responding?)
- Browser state (console errors? visual regressions?)

### Step 6: Verification

If verification is enabled (default), the verification pipeline runs all registered verifiers concurrently. Each verifier returns a `VerificationResult` (passed/failed + message).

The pipeline produces a `VerificationReport`. If `all_passed` is false and repair attempts remain, the harness constructs a repair prompt from the failure messages and recursively calls `run_turn` with the repair input. Default: 2 repair attempts.

### Step 7: Post-Turn Hooks

Same as pre-turn hooks, but triggered after the agent finishes. Common uses: notifications, artifact collection, metrics export.

### Step 8: Checkpoint

The thread state is serialized as a `Checkpoint` and saved to storage. This enables replay and recovery.

### Step 9: Turn End

The turn is marked as complete. The thread status is set to `COMPLETED`. Turn-end events are emitted.

---

## 4. How Tools Work

Tools are executable capabilities available to the agent. Each tool has:

- **name**: Unique identifier (e.g., `shell`, `file_read`, `file_write`)
- **description**: Human-readable description
- **category**: `read`, `write`, or `execute` -- determines policy behavior
- **input_schema**: JSON Schema describing accepted parameters
- **execute()**: Async method that performs the action and returns a `ToolResult`

### Built-in Tools

| Tool | Category | Description |
|------|----------|-------------|
| `shell` | execute | Run a shell command |
| `file_read` | read | Read a file's contents |
| `file_write` | write | Write content to a file |
| `search` | read | Search for text in files |
| `git_status` | read | Show git status |
| `test_runner` | execute | Run tests |
| `lint_runner` | execute | Run linter |
| `diff_tool` | read | Show file diffs |

### Tool Registry

The `ToolRegistry` holds all registered tools. It supports:

- Registering tool class instances
- Registering plain functions via the `@registry.tool()` decorator
- Querying by name
- Generating LLM-ready definitions (filtered by allowed/denied lists)

The registry auto-generates JSON Schema from Python function signatures and type hints using the `fn_to_json_schema()` utility.

### Adding a Custom Tool

1. Subclass `BaseTool`:

```python
from devharness.tools.base import BaseTool
from devharness.core.models import ToolCategory, ToolResult

class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something useful"
    category = ToolCategory.READ

    async def execute(self, query: str, limit: int = 10) -> ToolResult:
        # Your logic here
        result = do_something(query, limit)
        return self._ok(result)

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        }
```

2. Or use the decorator:

```python
from devharness.tools.registry import ToolRegistry
from devharness.core.models import ToolCategory, ToolResult

registry = ToolRegistry()

@registry.tool("my_tool", ToolCategory.READ, "Does something useful")
async def my_tool(query: str, limit: int = 10) -> ToolResult:
    result = do_something(query, limit)
    return ToolResult(output=result)
```

3. Register with the tool registry during bootstrap or via a skill.

---

## 5. How Approvals Work

Every tool call passes through the policy engine before execution. The policy engine evaluates in three stages:

### Stage 1: Denied/Allowed Lists

If the tool is in the thread's `denied_tools` list, it is immediately denied. If `allowed_tools` is set and the tool is not in it, it is denied.

### Stage 2: Mode Evaluation

The thread's `ApprovalMode` determines the baseline behavior:

| Mode | Read tools | Write tools | Execute tools |
|------|-----------|-------------|---------------|
| `full_trust` | Auto-approve | Auto-approve | Auto-approve |
| `auto_approve_safe` | Auto-approve | Require approval | Require approval |
| `approval_required` | Require approval | Require approval | Require approval |
| `read_only` | Auto-approve | Deny | Deny |
| `workspace_write` | Auto-approve | Auto-approve | Require approval |

### Stage 3: Custom Policy Rules

Built-in rules can override the mode decision:

- **DenyPathPatternRule**: Blocks writes to sensitive paths (`**/.env`, `**/credentials*`, `**/secrets*`).
- **DenyCommandRule**: Blocks dangerous shell commands (`rm -rf /`, `sudo`, `chmod 777`, `mkfs`, `dd`).
- **MaxFileSizeRule**: Blocks writes exceeding 1MB.

Custom rules subclass `PolicyRule` and implement `evaluate()`, returning a deny `PolicyDecision` or `None` to abstain.

### Approval Flow

When approval is required, the thread is paused (`ThreadStatus.PAUSED`) and an `ApprovalRequest` is created. The request can be resolved via:

- CLI: `harness approve <thread_id> <approval_id> --approve`
- Web UI: Click approve/deny
- Slack: Interactive buttons in the approval message

After resolution, the thread resumes.

---

## 6. How Verification and Repair Work

Verification runs after every turn (if enabled). The `VerificationPipeline` executes all registered `BaseVerifier` instances concurrently.

Each verifier returns a `VerificationResult`:

```python
class VerificationResult(BaseModel):
    verifier_name: str
    passed: bool
    message: str
    details: dict
    duration_ms: float
```

The pipeline aggregates results into a `VerificationReport`. If any verifier fails:

1. The harness constructs a repair prompt: "Verification failed. Fix the following issues:" followed by each failure message.
2. The harness calls `run_turn()` recursively with the repair prompt and `max_repair_attempts - 1`.
3. This continues until verification passes or repair attempts are exhausted.

Default: 2 repair attempts. This means the agent gets up to 3 total attempts (original + 2 repairs).

---

## 7. How Hooks Work

Hooks are shell scripts triggered at lifecycle events. They follow a strict exit-code contract:

| Exit Code | Meaning | Agent Impact |
|-----------|---------|-------------|
| 0 | Success | **Silent** -- output swallowed, no context pollution |
| 2 | Re-engage | Stdout injected into agent context as feedback |
| Other | Warning | Logged, execution continues |

This design is deliberate. When a formatting check passes, the agent does not need to know about it. When it fails, the agent receives the diff and can self-correct.

### Hook Events

| Event | When |
|-------|------|
| `pre_turn` | Before the agent starts work |
| `post_turn` | After the agent finishes |
| `pre_tool_call` | Before each tool execution |
| `post_tool_call` | After each tool execution |
| `pre_commit` | Before a git commit |
| `post_commit` | After a git commit |
| `on_error` | When the agent encounters an error |
| `on_idle` | When the agent has no more work |

### Hook Configuration

Hooks are defined as JSON in `.devharness/hooks/`:

```json
{
    "name": "format_check",
    "event": "pre_commit",
    "script": "ruff format --check . 2>&1 && exit 0 || { echo 'Formatting issues:'; ruff format --diff . 2>&1; exit 2; }",
    "enabled": true,
    "timeout": 60
}
```

The `on_tools` field (optional) restricts a hook to fire only after specific tool invocations:

```json
{
    "name": "test_after_write",
    "event": "post_tool_call",
    "script": "pytest --tb=short -q 2>&1 && exit 0 || { pytest --tb=short -q 2>&1; exit 2; }",
    "on_tools": ["file_write", "shell"],
    "timeout": 300
}
```

### Built-in Hook Factories

```python
from devharness.hooks.builtins import format_check_hook, typecheck_hook, test_hook

# Returns a HookConfig ready for registration
hook = format_check_hook(event=HookEvent.PRE_COMMIT)
hook = typecheck_hook(event=HookEvent.PRE_COMMIT)
hook = test_hook(event=HookEvent.POST_TOOL_CALL, on_tools=["file_write"])
```

### Context Injection

Hook scripts receive context via environment variables. The context dict passed to `run_hooks()` is stringified and set as env vars. For `PRE_TURN` hooks, this includes `thread_id` and `user_input`. For `POST_TURN` hooks, `thread_id` and `turn_id`.

---

## 8. How Skills Are Resolved

Skills are the primary unit of composition. Each skill bundles:

- A system prompt (persona-level instructions)
- A list of tool names the skill needs
- A list of verifier names the skill registers
- Optional hooks and context files

### Skill Directory Structure

```
skills/
  python-web/
    manifest.yaml
    prompt.md
```

**manifest.yaml:**

```yaml
name: python-web
version: "1.0.0"
description: "Python web application development"
tools:
  - shell
  - file_read
  - file_write
  - test_runner
  - lint_runner
verifiers:
  - pytest
  - ruff
context_files:
  - CLAUDE.md
  - docs/ARCHITECTURE.md
```

**prompt.md:**

```markdown
You are a Python web application developer. Follow these practices:
- Use FastAPI/Starlette for HTTP endpoints
- Write Pydantic models for all request/response schemas
- Write tests for every endpoint
- Run the linter after every code change
...
```

### Resolution Flow

1. Thread config specifies `skills: ["python-web", "testing"]`
2. The context architecture loads skill prompts via `SkillRegistry.get_combined_system_prompt()`
3. Each skill's system prompt is concatenated (separated by `---`)
4. The combined prompt is placed in Tier 2 (warm context)
5. If the budget is tight, older/less relevant Tier 2 content is trimmed

### Skill Loading

The `SkillLoader` discovers skills from configured directories:

1. Walk each directory in `config.skills_dirs`
2. Find subdirectories containing `manifest.yaml`
3. Parse the manifest, load `prompt.md` if present (else use `system_prompt` field)
4. Return `BaseSkill` instances for registration

---

## 9. How Observers Provide Feedback

Observers are the harness's sensory system. They watch the application under development and report findings as `Observation` objects.

### Observer Interface

```python
class BaseObserver(ABC):
    name: str

    async def observe(self, thread: Thread, turn: Turn | None) -> list[Observation]:
        """Run observation and return findings."""

    async def start(self) -> None:
        """Start continuous monitoring."""

    async def stop(self) -> None:
        """Stop continuous monitoring."""
```

### Observer Pipeline

The `ObserverPipeline` runs all registered observers concurrently after each turn:

1. For each observer, call `observe()` in its own task.
2. Collect all observations.
3. Emit each observation as an event on the bus.
4. Build an `ObservationSummary` from the raw observations.
5. Format the summary for agent context injection.

### Summary Format

The observation summary follows the "success silent, failures only" principle. Only noteworthy findings (warnings, errors, failures) are included:

```
[OBSERVATION REPORT - since your last action]
- Process: dev-server - crashed
- Tests: 42 passed, 3 failed, 0 errored
  - test_login: Expected 200, got 401
    at tests/test_auth.py:42
- logs: New RuntimeError in app.log
  TypeError: cannot unpack non-sequence NoneType
- No issues detected.    <-- only if everything is clean
```

### Built-in Observers

| Observer | What it watches |
|----------|----------------|
| `process` | Dev server and background process health (via psutil) |
| `test_obs` | Test runner results (pytest output) |
| `lint_obs` | Linter output (ruff, eslint) |
| `build` | Build status (compilation, bundling) |
| `logs` | Log file tailing for new errors |
| `endpoint` | HTTP endpoint health checks |
| `browser` | Browser state (console errors, visual regressions) |
| `metrics_obs` | Application metrics (response times, error rates) |

### Adding a Custom Observer

```python
from devharness.observers.base import BaseObserver
from devharness.core.models import Observation, ObservationSeverity, Thread, Turn

class DatabaseObserver(BaseObserver):
    name = "database"

    async def observe(self, thread: Thread, turn: Turn | None) -> list[Observation]:
        observations = []
        # Check for slow queries, connection pool health, etc.
        slow_queries = check_slow_queries()
        for q in slow_queries:
            observations.append(Observation(
                observer_name=self.name,
                thread_id=thread.id,
                turn_id=turn.id if turn else None,
                severity=ObservationSeverity.WARNING,
                title=f"Slow query: {q.duration_ms}ms",
                details=q.sql[:500],
            ))
        return observations

    async def start(self) -> None:
        pass  # start any background monitoring

    async def stop(self) -> None:
        pass  # clean up
```

Register with the pipeline:

```python
pipeline.add_observer(DatabaseObserver())
```

---

## 10. How Browser Testing Is Fused Into the Loop

Browser testing is not a separate CI step. It runs inside the harness verification loop so the agent can see frontend failures and self-correct.

### How It Works

1. Agent writes frontend code.
2. Post-tool hook detects UI file changes and triggers the browser observer.
3. The `BrowserTestRunner` launches headless Chromium via Playwright.
4. The runner navigates to the specified URL and executes steps.
5. Screenshots are saved as artifacts. Console errors and DOM snapshots are captured.
6. Results are structured as `BrowserTestResult` and injected into agent context.
7. If a test fails, the agent sees exactly what went wrong and where.

### Interaction Flow YAML

Browser tests are defined declaratively in YAML:

```yaml
name: login_flow
url: http://localhost:3000/login
viewport_width: 1280
viewport_height: 720
steps:
  - action: fill
    selector: "input[name='email']"
    value: "test@example.com"
  - action: fill
    selector: "input[name='password']"
    value: "testpass123"
  - action: click
    selector: "button[type='submit']"
  - action: wait_for
    selector: ".dashboard"
    timeout: 5000
  - action: screenshot
    name: "after_login"
assertions:
  - type: url_contains
    value: "/dashboard"
  - type: element_visible
    selector: ".welcome-message"
  - type: no_console_errors
```

### Available Step Actions

| Action | Parameters | Description |
|--------|-----------|-------------|
| `click` | `selector` | Click an element |
| `fill` | `selector`, `value` | Fill an input field |
| `type` | `selector`, `value` | Type into an element character by character |
| `wait_for` | `selector`, `timeout` | Wait for an element to appear |
| `screenshot` | `name` | Capture a screenshot |
| `navigate` | `value` | Navigate to a URL |
| `select` | `selector`, `value` | Select an option in a dropdown |
| `hover` | `selector` | Hover over an element |
| `wait` | `timeout` | Wait for a duration (ms) |

### Available Assertion Types

| Type | Parameters | Description |
|------|-----------|-------------|
| `url_contains` | `value` | Current URL contains the string |
| `element_visible` | `selector` | Element exists and is visible |
| `no_console_errors` | | No console errors detected |
| `text_contains` | `selector`, `value` | Element text contains the string |

### Failure Context

When a browser test fails, the agent receives:

- The step that failed and why
- Console errors captured during the flow
- A text-rasterized DOM snapshot (HTML stripped to text, max 5000 chars)
- Screenshot artifact paths

This gives the agent enough context to diagnose and fix the issue without human intervention.

---

## 11. How Context Tiers Work

The context architecture manages what information the agent sees. Three tiers target 40% context window utilization.

### Why 40%?

When context utilization is too high, model performance degrades -- the model struggles to find relevant information in noise. When utilization is too low, the model lacks needed context. Research has found 40% to be a productive sweet spot: enough information to work effectively, enough headroom for reasoning.

### Tier 1: Hot (Always Loaded)

Content that is always present in every turn:

- Base system prompt (default or override)
- Project context files (CLAUDE.md, AGENTS.md, architecture docs)

These files are loaded from the workspace root. They define the project constitution -- rules the agent must always follow.

Token cost is tracked as `budget.tier1_tokens`.

### Tier 2: Warm (Task-Activated)

Content loaded based on the current task:

- Current task instruction (`"Current task: fix the tests"`)
- Active skill prompts (concatenated from selected skills)
- Observation summaries (from the most recent observer run)

Tier 2 is trimmed to fit within the remaining budget after Tier 1. The trimming strategy drops the oldest items first.

Token cost is tracked as `budget.tier2_tokens`.

### Tier 3: Cold (On-Demand)

Content that is never pre-loaded into the context window. The agent accesses it via tools during execution:

- File reads (`file_read` tool)
- Codebase search (`search` tool)
- Memory queries (`memory_query`, `memory_search` tools)
- External documentation

Cold content contributes 0 tokens to the budget. The model pulls what it needs when it needs it.

### Token Estimation

Token estimation uses a conservative heuristic: approximately 4 characters per token. This intentionally over-estimates so the harness stays within budget rather than exceeding it.

```python
def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
```

### Budget Tracking

The `ContextBudget` model tracks:

```python
class ContextBudget(BaseModel):
    max_tokens: int = 200_000
    tier1_tokens: int = 0
    tier2_tokens: int = 0
    tier3_tokens: int = 0
    utilization_target: float = 0.40
```

Properties: `used_tokens`, `remaining`, `utilization`.

---

## 12. How to Add a Custom Tool

See the Tools section above for the full pattern. Summary:

1. Subclass `BaseTool` or use the `@registry.tool()` decorator.
2. Set `name`, `description`, and `category`.
3. Implement `execute(**kwargs) -> ToolResult`.
4. Implement `get_input_schema() -> dict` (or let the decorator generate it from type hints).
5. Register with the `ToolRegistry`.

Key considerations:

- Set `category` correctly -- it determines approval behavior.
- Use `self._ok(output)` for success, `self._error(message)` for errors.
- Use `self._truncated(output, max_bytes)` for large outputs.
- The JSON Schema is used by the LLM to understand available parameters.

---

## 13. How to Add a Custom Skill

1. Create a directory under `skills/`:

```
skills/my-skill/
  manifest.yaml
  prompt.md
```

2. Write `manifest.yaml`:

```yaml
name: my-skill
version: "0.1.0"
description: "My custom skill"
tools:
  - file_read
  - file_write
  - shell
verifiers:
  - pytest
hooks:
  post_tool_call:
    script: "run-checks.sh"
context_files:
  - docs/my-guide.md
```

3. Write `prompt.md` with the system prompt for this skill.

4. The skill loader discovers it automatically from configured `skills_dirs`.

5. Activate in a thread:

```bash
harness run "do the thing" --skill my-skill
```

Or programmatically:

```python
config = ThreadConfig(skills=["my-skill"])
thread = await runtime.create_thread(config)
```

---

## 14. How to Add a Custom Observer

1. Subclass `BaseObserver`:

```python
class MyObserver(BaseObserver):
    name = "my_observer"

    async def observe(self, thread, turn):
        # Return list[Observation]
        ...

    async def start(self):
        ...

    async def stop(self):
        ...
```

2. Register with the observer pipeline:

```python
pipeline.add_observer(MyObserver())
```

3. Observations are automatically collected after each turn and injected into agent context.

---

## 15. How to Create Browser Test Flows

1. Create a YAML file in `.devharness/browser_tests/`:

```yaml
name: signup_flow
url: http://localhost:3000/signup
steps:
  - action: fill
    selector: "#email"
    value: "new@example.com"
  - action: fill
    selector: "#password"
    value: "secure123"
  - action: click
    selector: "button[type='submit']"
  - action: wait_for
    selector: ".welcome"
    timeout: 10000
assertions:
  - type: url_contains
    value: "/welcome"
  - type: no_console_errors
```

2. Run manually:

```bash
harness browser-test
```

3. Or integrate via the browser observer, which runs flows automatically after UI file changes.

4. Install Playwright if not present:

```bash
pip install playwright
playwright install
```

---

## 16. How to Operate in Safe vs Permissive Modes

### Safe Mode (`approval_required`)

Every tool call requires explicit approval. Use for sensitive operations or unfamiliar codebases.

```bash
harness run "refactor the auth module" --approval-mode approval_required
```

Approvals can be handled via CLI, web UI, or Slack.

### Moderate Mode (`auto_approve_safe`)

Default. Read tools auto-approve. Write and execute tools require approval.

### Permissive Mode (`full_trust`)

All tool calls auto-approve. Use when you trust the agent and want maximum speed.

```bash
harness run "fix all lint warnings" --approval-mode full_trust
```

### Read-Only Mode (`read_only`)

Only read tools are allowed. Write and execute tools are denied outright. Use for research and analysis tasks.

### Workspace Write Mode (`workspace_write`)

Read and write auto-approve. Only execute (shell commands) requires approval. A middle ground for code changes without running arbitrary commands.

### Custom Safety Rules

Add policy rules to block specific patterns regardless of mode:

- `DenyPathPatternRule`: Block writes to `.env`, `credentials*`, `secrets*`.
- `DenyCommandRule`: Block `rm -rf /`, `sudo`, `chmod 777`, etc.
- `MaxFileSizeRule`: Block writes over 1MB.

These rules fire after mode evaluation and can deny what the mode would allow.

---

## 17. Troubleshooting

### Agent CLI not found

```
AgentError: claude CLI not found at 'claude'. Install it or set cli_path explicitly.
```

The agent backend runs `claude` or `codex` as a subprocess. Ensure the CLI is installed and on your `$PATH`. Or set `cli_path` in the backend configuration.

### Thread already running

```
ThreadAlreadyRunningError: Thread abc123 is already running
```

A thread can only run one turn at a time. Wait for the current turn to complete, or cancel the thread:

```bash
# Cancel is available via the runtime API
```

### Verification loop exhausted

If verification keeps failing after all repair attempts, the thread completes with the last verification report attached. Check `turn.verification.results` for details.

### Hook timeout

Hooks have a configurable timeout (default 60s). If a hook times out, it returns exit code -1 and a warning is logged. Increase the timeout in the hook config or optimize the script.

### Playwright not installed

```
BrowserTestResult(passed=False, failure_reason="Playwright not installed...")
```

Install the browser testing dependencies:

```bash
pip install devharness[browser]
playwright install
```

### Memory backend unavailable

The harness degrades gracefully when Neo4j or Obsidian is unavailable. Writes are silently dropped. Reads return empty results. The agent continues working normally.

### Events not persisting

Check that the storage backend is initialized (`await storage.initialize()`). The bootstrap function handles this automatically.

---

## 18. Glossary

| Term | Definition |
|------|-----------|
| **Agent Backend** | A pluggable wrapper around a CLI agent (Claude Code, Codex). Implements `AgentBackend` ABC. |
| **Approval Mode** | One of five modes controlling which tool calls require explicit approval. |
| **Artifact** | A generated output stored by the harness (patch, screenshot, plan, report). |
| **Bootstrap** | The process of wiring all harness components together at startup. |
| **Checkpoint** | A serializable snapshot of a thread for persistence and replay. |
| **Cold Context** | Tier 3: information accessed on-demand via tools, never pre-loaded. |
| **Context Architecture** | The system that assembles tiered context within a token budget. |
| **Context Budget** | Token tracking model with max, per-tier usage, and utilization target. |
| **Context Firewall** | Isolation between parent and sub-agent context windows. Sub-agent tool calls do not surface in the parent thread. |
| **Enforcement Rule** | A mechanical check (linter, type checker) with agent-readable correction prompts. |
| **Event** | A structured log entry emitted by the harness. Keyed by `EventKind`. |
| **Event Bus** | In-process async pub/sub system. Every significant action emits an event. |
| **Feedforward Control** | Guidance given to the agent before it acts (system prompts, rules, docs). |
| **Feedback Control** | Checks run after the agent acts (tests, observers, verifiers). |
| **Hook** | A shell script triggered at a lifecycle event. Exit 0 = silent, exit 2 = re-engage. |
| **Hot Context** | Tier 1: always loaded (system prompt, project constitution). |
| **Observation** | A structured finding from an observer (info, warning, error, critical). |
| **Observer** | A monitor that watches an aspect of the application and produces observations. |
| **Plan** | A structured plan with trackable steps, created during task decomposition. |
| **Policy Decision** | The result of evaluating a tool call: allowed, denied, or requires approval. |
| **Policy Engine** | Evaluates tool calls against mode + custom rules. |
| **Policy Rule** | A custom rule that can deny specific tool invocations. |
| **Re-engage** | When a hook exits with code 2, its stdout is injected into agent context. |
| **Repair** | Automatic re-delegation after verification failure with failure context. |
| **Skill** | A composable pack: system prompt + tool set + verifiers. |
| **Sub-Agent** | An isolated agent instance spawned for a specific subtask. |
| **Task DAG** | A dependency graph of tasks for parallel execution. |
| **Thread** | A session container. The top-level unit of work. |
| **Tool** | An executable capability available to the agent. Categorized as read/write/execute. |
| **Turn** | One cycle of agent work within a thread. |
| **Verification** | Post-turn checks that determine if the agent's work is correct. |
| **Warm Context** | Tier 2: task-activated content (skill prompts, observations). |
