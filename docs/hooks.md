# Hooks System

Hooks are shell scripts triggered at agent lifecycle events. They provide deterministic control flow around the agent's actions -- running formatters, type checkers, test suites, notifications, and custom validation at precise points in the lifecycle.

---

## Exit Code Contract

Every hook follows a strict exit-code protocol:

| Exit Code | Meaning | Agent Impact |
|-----------|---------|-------------|
| **0** | Success | **Silent.** Output is swallowed. The agent never sees it. This prevents context pollution -- when a formatting check passes, the agent does not need to know. |
| **2** | Re-engage | **Stdout is injected into the agent's context** as feedback. The agent receives the hook's output and can act on it. Use this when the hook detects a problem the agent should fix. |
| **Other** | Warning | Logged as a warning. Execution continues. The agent is not informed. |

This design is the foundation of the hook system. Understand it before writing hooks.

### Why Success Is Silent

If every passing check injected its output into the agent's context, the context window would fill with noise. The agent would see "Formatting OK. Tests passing. Types clean." repeatedly and eventually stop paying attention to the important signals. By swallowing success, only failures reach the agent, keeping the signal-to-noise ratio high.

### Why Exit 2 Re-engages

When a hook detects a problem, the agent needs to know what went wrong and how to fix it. Exit code 2 pipes the hook's stdout into the agent's context. The hook author controls exactly what information the agent receives -- the diff, the error messages, the failing test output.

---

## Hook Events

| Event | When It Fires | Common Uses |
|-------|--------------|------------|
| `pre_turn` | Before the agent starts work on a turn | Inject dynamic context, check preconditions |
| `post_turn` | After the agent finishes a turn | Send notifications, collect metrics, run audits |
| `pre_tool_call` | Before each tool execution | Validate tool arguments, log tool usage |
| `post_tool_call` | After each tool execution | Run tests after file writes, check formatting |
| `pre_commit` | Before a git commit | Run formatters, type checkers, linters |
| `post_commit` | After a git commit | Deploy preview, notify team, update tracking |
| `on_error` | When the agent encounters an error | Alert on-call, capture diagnostic info |
| `on_idle` | When the agent has no more work | Trigger cleanup, generate reports |

---

## Hook Configuration

### JSON File Format

Hooks are defined as JSON files in `.devharness/hooks/`:

```json
{
    "name": "format_check",
    "event": "pre_commit",
    "script": "ruff format --check . 2>&1 && exit 0 || { echo 'Formatting issues:'; ruff format --diff . 2>&1; exit 2; }",
    "enabled": true,
    "timeout": 60,
    "on_tools": null,
    "config": {}
}
```

A single JSON file can contain an array of hook configs:

```json
[
    {
        "name": "format_check",
        "event": "pre_commit",
        "script": "ruff format --check . 2>&1 && exit 0 || { ruff format --diff . 2>&1; exit 2; }"
    },
    {
        "name": "typecheck",
        "event": "pre_commit",
        "script": "mypy . 2>&1 && exit 0 || { mypy . 2>&1; exit 2; }"
    }
]
```

### HookConfig Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | | Unique hook identifier |
| `event` | string | Yes | | Lifecycle event to trigger on |
| `script` | string | Yes | | Shell script or command to execute |
| `enabled` | bool | No | `true` | Whether the hook is active |
| `on_tools` | list or null | No | `null` | Only trigger for these tool names (for `pre_tool_call`/`post_tool_call`) |
| `timeout` | int | No | `60` | Maximum execution time in seconds |
| `config` | dict | No | `{}` | Additional configuration passed to the script |

### Tool Filtering with on_tools

For `post_tool_call` hooks, the `on_tools` field restricts which tool invocations trigger the hook:

```json
{
    "name": "test_after_write",
    "event": "post_tool_call",
    "script": "pytest --tb=short -q 2>&1 && exit 0 || { pytest --tb=short -q 2>&1; exit 2; }",
    "on_tools": ["file_write"],
    "timeout": 300
}
```

This hook only runs after `file_write` tool calls, not after `file_read` or `search`. Use this to run tests only when code changes, not on every read.

---

## Hook Execution

### Environment Variables

Hook scripts receive context via environment variables. All values in the context dict are stringified:

For `pre_turn`:

| Variable | Description |
|----------|-------------|
| `thread_id` | Current thread ID |
| `user_input` | The user's prompt |

For `post_turn`:

| Variable | Description |
|----------|-------------|
| `thread_id` | Current thread ID |
| `turn_id` | Current turn ID |

### Execution Order

Hooks for the same event run **sequentially** in registration order. If any hook exits with code 2, execution stops and the re-engagement result is returned immediately. Remaining hooks for that event are skipped.

### Timeout Handling

If a hook exceeds its timeout, it is killed and returns exit code -1 with a timeout warning. The agent is not informed (only logged).

### Error Handling

If a hook script cannot be executed (e.g., `sh` not found, permission denied), exit code -1 is returned and the error is logged. The harness continues.

---

## Built-in Hook Factories

The `devharness.hooks.builtins` module provides factory functions that return pre-configured `HookConfig` objects:

### format_check_hook

Runs `ruff format --check`. On failure, re-engages with the formatting diff.

```python
from devharness.hooks.builtins import format_check_hook
from devharness.core.models import HookEvent

hook = format_check_hook(event=HookEvent.PRE_COMMIT, timeout=60)
```

Script:

```bash
ruff format --check . 2>&1 && exit 0 || { echo 'Formatting issues detected:'; ruff format --diff . 2>&1; exit 2; }
```

### typecheck_hook

Runs `mypy`. On failure, re-engages with the type error output.

```python
hook = typecheck_hook(event=HookEvent.PRE_COMMIT, timeout=120)
```

### test_hook

Runs `pytest`. On failure, re-engages with the test output.

```python
hook = test_hook(
    event=HookEvent.POST_TOOL_CALL,
    on_tools=["file_write", "shell"],
    timeout=300,
)
```

---

## Hook Discovery

The `HookRegistry` can discover hooks from the filesystem:

```python
from devharness.hooks.registry import HookRegistry

registry = HookRegistry()
count = registry.load_from_directory("/path/to/workspace")
# Loads from /path/to/workspace/.devharness/hooks/*.json
```

Malformed JSON files are logged as warnings and skipped.

### Programmatic Registration

```python
from devharness.core.models import HookConfig, HookEvent

registry.register(HookConfig(
    name="my_hook",
    event=HookEvent.POST_TURN,
    script="echo 'Turn complete' | slack-notify",
    timeout=30,
))
```

---

## Writing Effective Hooks

### Pattern: Format Check

```bash
# Check formatting. If clean: exit 0 (silent).
# If dirty: show diff and exit 2 (re-engage agent with the diff).
ruff format --check . 2>&1 && exit 0 || { ruff format --diff . 2>&1; exit 2; }
```

### Pattern: Test Suite

```bash
# Run tests. If all pass: exit 0 (silent).
# If failures: show output and exit 2 (agent sees what failed).
pytest --tb=short -q 2>&1 && exit 0 || { pytest --tb=short -q 2>&1; exit 2; }
```

### Pattern: Type Check

```bash
mypy src/ 2>&1 && exit 0 || { mypy src/ 2>&1; exit 2; }
```

### Pattern: Notification (Fire and Forget)

```bash
# Always exit 0 -- never re-engage the agent for notifications
curl -X POST https://hooks.slack.com/services/... \
  -d "{\"text\": \"Turn $turn_id completed in thread $thread_id\"}" \
  2>/dev/null
exit 0
```

### Pattern: Precondition Check

```bash
# Pre-turn hook: ensure the dev server is running
if ! curl -s http://localhost:3000/health > /dev/null 2>&1; then
    echo "Dev server is not running. Start it with: npm run dev"
    exit 2
fi
exit 0
```

### Pattern: Architecture Enforcement

```bash
# Check that no files in src/core/ import from src/ui/
if grep -r "from src.ui" src/core/ 2>/dev/null; then
    echo "Architecture violation: core/ must not import from ui/"
    grep -rn "from src.ui" src/core/
    exit 2
fi
exit 0
```

---

## Debugging Hooks

### Check Registered Hooks

```bash
harness hooks
```

### Test a Hook Manually

Run the script directly to verify its behavior:

```bash
# Should exit 0 if formatting is clean
ruff format --check . 2>&1 && exit 0 || { ruff format --diff . 2>&1; exit 2; }
echo "Exit code: $?"
```

### Check Logs

Hooks log at INFO level (registration, re-engagement) and WARNING level (non-zero exits, timeouts, errors). Set `--log-level DEBUG` for maximum visibility.
