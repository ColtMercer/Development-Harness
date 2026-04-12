# Architecture Deep-Dive

This document describes the internal architecture of the Development Harness: module structure, data flow, key design decisions, and extension points.

---

## Module Map

```
src/devharness/
  __init__.py
  _types.py                  # Shared type aliases
  bootstrap.py               # Component wiring -- assembles Runtime from config

  core/
    models.py                # ALL Pydantic domain models (single file, no circular imports)
    runtime.py               # Runtime orchestrator -- the agent loop
    event_bus.py             # In-process async pub/sub
    errors.py                # Exception hierarchy (HarnessError base)
    config.py                # HarnessConfig + env var loading

  agents/
    base.py                  # AgentBackend ABC
    claude_code.py           # Claude Code subprocess backend
    codex.py                 # Codex subprocess backend
    sub_agent.py             # Sub-agent pool with context firewalls
    output_parser.py         # Parse streaming JSON -> AgentEvent

  tools/
    base.py                  # BaseTool ABC
    registry.py              # ToolRegistry + @tool decorator
    schema.py                # Python type hints -> JSON Schema
    builtin/
      shell.py               # Shell command execution
      file_read.py           # File reading
      file_write.py          # File writing
      search.py              # Text search in files
      git_status.py          # Git status
      test_runner.py         # Test execution
      lint_runner.py         # Linter execution
      diff_tool.py           # File diffs

  hooks/
    engine.py                # HookEngine -- subprocess execution
    registry.py              # HookRegistry -- registration and discovery
    builtins.py              # Built-in hook factories (format, typecheck, test)

  policies/
    engine.py                # PolicyEngine -- mode + rules evaluation
    modes.py                 # Per-mode evaluation helpers
    rules.py                 # Built-in policy rules (path deny, command deny, size limit)

  observers/
    base.py                  # BaseObserver ABC
    pipeline.py              # ObserverPipeline -- concurrent execution
    summary.py               # Build and format ObservationSummary
    process.py               # Process health observer
    test_obs.py              # Test result observer
    lint_obs.py              # Linter output observer
    build.py                 # Build status observer
    logs.py                  # Log file tailing observer
    endpoint.py              # HTTP endpoint health observer
    browser.py               # Browser state observer
    metrics_obs.py           # Application metrics observer

  verification/
    pipeline.py              # VerificationPipeline -- concurrent verifier execution
    verifiers/               # Concrete verifier implementations

  context/
    architecture.py          # ContextArchitecture -- tiered context builder
    budget.py                # Token estimation, trimming, summary formatting
    loader.py                # Load context files and skill prompts

  skills/
    base.py                  # BaseSkill ABC
    registry.py              # SkillRegistry -- registration and lookup
    loader.py                # SkillLoader -- filesystem discovery
    builtin/                 # Built-in skills

  tasks/
    dag.py                   # TaskDAGManager -- build and mutate dependency graphs
    executor.py              # Task executor -- parallel dispatch
    planner.py               # Task planner -- decompose goals into DAGs

  memory/
    service.py               # MemoryService facade + MemoryBackend ABC
    obsidian/
      backend.py             # Obsidian vault memory backend
      vault.py               # Read/write/search Markdown files
      frontmatter.py         # YAML frontmatter parsing
    ingestion/               # Event ingestion pipeline
    consolidation/           # Daily/weekly summary generation
    retrieval/
      context_builder.py     # Build memory context for agent
    tools/                   # Memory query tools for agents

  enforcement/
    engine.py                # EnforcementEngine -- run architectural checks
    rules.py                 # Enforcement rule definitions
    linter_bridge.py         # Bridge to external linters

  storage/
    base.py                  # StorageBackend ABC
    sqlite.py                # SQLite implementation
    database.py              # Low-level database utilities
    migrations/
      runner.py              # Migration runner

  artifacts/
    manager.py               # ArtifactManager -- create and list artifacts

  browser_testing/
    runner.py                # BrowserTestRunner -- Playwright execution
    flows.py                 # Load YAML flow definitions
    screenshots.py           # Screenshot management
    dom.py                   # DOM snapshot utilities
    assertions.py            # Assertion checking
    accessibility.py         # Accessibility checks

  integrations/
    slack/                   # Slack Socket Mode integration

  app_server/
    http_server.py           # Starlette HTTP server + SSE

  cli/
    main.py                  # Click CLI entry point

  ui/                        # Web UI templates and static assets

  telemetry/
    logger.py                # Logging setup

  templates/                 # Project templates (python-web, python-cli, generic)
```

---

## Data Flow Diagrams

### Turn Execution Flow

```
User Input
    |
    v
+---+---+
| Thread |  <-- create or lookup
+---+---+
    |
    v
+--------+
|Pre-Turn|  <-- HookEngine runs PRE_TURN hooks
| Hooks  |      exit 0: silent / exit 2: inject stdout into prompt
+---+----+
    |
    v
+---------+
| Context |  <-- ContextArchitecture.build_context()
| Assembly|      Tier 1: system prompt + context files
|         |      Tier 2: task + skills + observations (trimmed to budget)
+----+----+      Tier 3: not loaded (accessed via tools)
     |
     v
+----+----+
| Agent   |  <-- AgentBackend.run_task()
| Backend |      Subprocess: claude/codex CLI
| (stream)|      Yields: AgentEvent (text, tool_call, tool_result, done, error)
+----+----+
     |
     v
+----+-----+
| Observer |  <-- ObserverPipeline.observe_all()
| Pipeline |      Concurrent: process, test, lint, build, logs, endpoint, browser
+----+-----+      Returns: list[Observation]
     |
     v
+----+------+
|Verification|  <-- VerificationPipeline.run()
| Pipeline   |      Concurrent verifiers
+----+-------+      Returns: VerificationReport
     |
     +-- all_passed? -- yes --> Post-Turn Hooks --> Checkpoint --> Done
     |
     +-- no? + repairs left --> Construct repair prompt --> run_turn() [recursive]
     |
     +-- no? + no repairs  --> Complete with failure report
```

### Event Flow

```
Runtime                  EventBus                 Subscribers
  |                         |                         |
  |--- emit(Event) -------->|                         |
  |                         |--- handler(Event) ----->| StorageBackend.save_event()
  |                         |--- handler(Event) ----->| SlackIntegration.on_event()
  |                         |--- handler(Event) ----->| WebUI.sse_push()
  |                         |                         |
  |                         |  (concurrent via anyio   |
  |                         |   task group; failures   |
  |                         |   logged, not propagated)|
```

### Context Assembly Flow

```
                   ContextArchitecture.build_context()
                              |
        +---------------------+---------------------+
        |                     |                     |
   Tier 1 (Hot)          Tier 2 (Warm)         Tier 3 (Cold)
   Always loaded         Task-activated        On-demand
        |                     |                     |
   System prompt         Task instruction      file_read tool
   Context files         Skill prompts         search tool
   (CLAUDE.md, etc.)     Observations          memory_query tool
        |                     |                     |
        +--- estimate_tokens --+                    |
        |                     |                 (0 tokens)
        +-- trim_to_budget ---+
        |                     |
        v                     v
   AgentContext.system_prompt  AgentContext.instructions
                               AgentContext.observation_summary
```

### Policy Evaluation Flow

```
Tool Call (name, args, category)
    |
    v
Denied tools list? --> yes --> DENY
    |
    no
    v
Allowed tools list set? --> yes, tool not in list --> DENY
    |
    no (or tool in list)
    v
Mode evaluation (full_trust / auto_approve_safe / ...)
    |
    +-- denied by mode --> DENY
    +-- requires approval --> APPROVAL_REQUIRED
    +-- allowed --> continue
    |
    v
Custom policy rules (DenyPathPattern, DenyCommand, MaxFileSize)
    |
    +-- any rule denies --> DENY
    +-- all abstain --> ALLOW
```

---

## Key Design Decisions

### 1. All Models in a Single File

All Pydantic domain models live in `core/models.py`. This prevents circular imports -- models reference each other heavily (Thread contains Turns, Turns contain ToolCalls, etc.). Having them in one file means any module can import any model without import cycles.

### 2. Agent Backends as Subprocesses

Agent backends run Claude Code and Codex as subprocesses, not via API. This means:

- The harness works with the same CLI tools developers already have installed.
- No API key management for the agent runtime (the CLI handles its own auth).
- Streaming JSON output is parsed line by line into `AgentEvent` objects.
- Cancellation is handled via SIGTERM/SIGKILL.

### 3. Event Bus as the Nervous System

The event bus decouples producers from consumers. The runtime emits events without knowing who is listening. This enables:

- Persisting all events to storage without the runtime knowing about storage.
- Pushing events to Slack, the web UI, or any other subscriber.
- Adding new integrations without modifying the runtime.

Failures in subscribers are isolated. A crashing Slack handler does not break the agent loop.

### 4. SQLite Over Config Files

Configuration lives in the SQLite database, not in YAML files. This prevents:

- Accidentally committing API keys to source control.
- Config file format bikeshedding.
- Drift between config and actual state.

Environment variables with `DEVHARNESS_` prefix override database values for CI/deployment use cases.

### 5. 40% Context Utilization Target

The context architecture targets 40% utilization rather than maximizing context usage. When everything is described as important, the model stops following rules. The 40% target keeps Tier 1 (project constitution) concise and leaves headroom for the model to reason.

### 6. Success Silent, Failure Re-engage

Hooks use exit code semantics (0 = silent, 2 = re-engage) to prevent context pollution. When a formatting check passes, the agent does not need to know. When it fails, the diff is injected into context. This keeps the agent focused on actual problems.

### 7. Concurrent Observer and Verifier Execution

Observers and verifiers run concurrently via `anyio.create_task_group()`. Each runs in its own task. Failures are caught per-observer/verifier so one failure does not cancel the others or the pipeline.

### 8. Graceful Memory Degradation

Memory backends (Neo4j, Obsidian) are enhancements, not dependencies. The `MemoryService` facade catches all backend exceptions and:

- Drops writes silently.
- Returns empty results for reads.
- Never interrupts the agent.

Events are buffered in SQLite when Neo4j is unavailable and replayed when connectivity is restored.

### 9. Recursive Repair

Verification failures trigger recursive `run_turn()` calls with repair context. This is bounded by `max_repair_attempts` (default 2) to prevent infinite loops. The repair prompt includes specific failure messages so the agent knows exactly what to fix.

---

## Extension Points

### Add a New Agent Backend

Implement `AgentBackend`:

```python
class MyBackend(AgentBackend):
    async def run_task(self, prompt, context, tools, constraints) -> AsyncIterator[AgentEvent]:
        # Spawn your agent and yield events
        ...

    async def cancel(self) -> None:
        # Cancel the running agent
        ...

    async def health_check(self) -> bool:
        # Check if the agent CLI is available
        ...
```

Register in `bootstrap.py`:

```python
agent_backends["my-backend"] = MyBackend()
```

### Add a New Storage Backend

Implement `StorageBackend`. All methods are async. See `storage/base.py` for the full interface.

### Add a New Observer

See `observers/base.py`. Register with `ObserverPipeline.add_observer()`.

### Add a New Verifier

Implement `BaseVerifier` (see `verification/`). Register with `VerificationPipeline.add_verifier()`.

### Add a New Policy Rule

Subclass `PolicyRule`:

```python
class MyRule(PolicyRule):
    name = "my_rule"

    def evaluate(self, tool_name, arguments, category) -> PolicyDecision | None:
        if should_deny(tool_name, arguments):
            return PolicyDecision(allowed=False, mode=..., reason="...")
        return None  # abstain
```

Pass to `PolicyEngine(extra_rules=[MyRule()])`.

### Add a New Skill

Create a directory with `manifest.yaml` + `prompt.md`. Or subclass `BaseSkill` for programmatic skills.

### Add a New Tool

Subclass `BaseTool` or use `@registry.tool()` decorator.

### Add a New Hook

Create a JSON file in `.devharness/hooks/` or register programmatically via `HookRegistry.register()`.

### Add a New Memory Backend

Implement `MemoryBackend`:

```python
class MyMemoryBackend(MemoryBackend):
    async def ingest_event(self, event: dict) -> None: ...
    async def query(self, query: str, **kwargs) -> list[dict]: ...
    async def search(self, text: str, *, limit: int = 10) -> list[dict]: ...
    async def consolidate_daily(self, day: date | None = None) -> None: ...
    async def health_check(self) -> bool: ...
```

Pass to `MemoryService(backend=MyMemoryBackend())`.
