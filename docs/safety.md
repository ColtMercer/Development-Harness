# Safety and Approval Guide

This document explains how the Development Harness controls what agents can do, how approval decisions are made, and how to configure safety boundaries for your environment.

---

## Philosophy

The harness operates on the principle that agents should be constrained by default and granted trust explicitly. Every tool call passes through the policy engine before execution. The policy engine is the gatekeeper between the agent's intent and actual side effects.

Safety is not binary. The harness provides a spectrum from full lockdown (read-only) to full autonomy (full trust), with meaningful intermediate modes that match real-world workflows.

---

## Approval Modes

Each thread has an `ApprovalMode` that determines baseline behavior for tool calls.

### full_trust

All tool calls are auto-approved. No human intervention required.

**Use when:** You trust the agent, the workspace is disposable (feature branch, container), and you want maximum speed. Appropriate for well-understood tasks with strong verification (tests, linters) in the loop.

**Risk:** The agent can execute arbitrary commands and write to any file.

### auto_approve_safe (default)

Read tools are auto-approved. Write and execute tools require explicit user approval.

**Use when:** General development. The agent can read and search freely, but you review changes before they happen.

**Risk:** Low. The agent cannot modify files or run commands without your consent.

### approval_required

Every tool call requires explicit user approval, including reads.

**Use when:** Sensitive codebases, compliance requirements, or when onboarding a new agent setup and you want to observe every action.

**Risk:** Very low, but slow. Every action blocks on human input.

### read_only

Only read-category tools are allowed. Write and execute tools are denied outright (not held for approval -- denied).

**Use when:** Research and analysis tasks. The agent can explore the codebase but cannot change anything.

**Risk:** None. The agent has no side effects.

### workspace_write

Read and write tools are auto-approved. Execute tools (shell commands) require approval.

**Use when:** You trust the agent to modify files but want to review commands before execution. A practical middle ground for code generation tasks where the agent needs to write code but should not run arbitrary processes.

**Risk:** The agent can write to any file, but cannot run commands without approval.

---

## Tool Categories

Every tool is assigned a category that determines how it interacts with approval modes:

| Category | Description | Examples |
|----------|-------------|---------|
| `read` | Inspects state, no side effects | `file_read`, `search`, `git_status`, `diff_tool` |
| `write` | Modifies files | `file_write` |
| `execute` | Runs processes, arbitrary commands | `shell`, `test_runner`, `lint_runner` |

The category is set by the tool author in the tool definition. Miscategorizing a tool (e.g., labeling a write tool as read) undermines the safety model.

---

## Policy Rules

Policy rules run after mode evaluation and can deny tool calls that the mode would otherwise allow. Rules provide defense-in-depth: even in `full_trust` mode, you can deny specific dangerous patterns.

### DenyPathPatternRule

Blocks writes to file paths matching glob patterns.

**Default patterns:**

```
**/.env
**/.env.*
**/credentials*
**/secrets*
```

Any `write`-category tool call targeting a path matching these patterns is denied, regardless of approval mode.

**Customization:**

```python
from devharness.policies.rules import DenyPathPatternRule

rule = DenyPathPatternRule(patterns=[
    "**/.env",
    "**/.env.*",
    "**/credentials*",
    "**/secrets*",
    "**/private_key*",
    "**/*.pem",
    "**/config/production*",
])
```

### DenyCommandRule

Blocks shell commands matching dangerous regex patterns.

**Default patterns:**

| Pattern | Blocks |
|---------|--------|
| `\brm\s+-rf\s+/` | Recursive deletion from root |
| `\bsudo\b` | Privilege escalation |
| `\bchmod\s+777\b` | World-writable permissions |
| `\bmkfs\b` | Filesystem creation |
| `\bdd\s+if=` | Raw disk operations |

Only applies to the `shell` tool. Inspects the `command` argument.

**Customization:**

```python
from devharness.policies.rules import DenyCommandRule

rule = DenyCommandRule(patterns=[
    r"\brm\s+-rf\s+/",
    r"\bsudo\b",
    r"\bcurl\b.*\|.*\bsh\b",  # pipe curl to shell
    r"\bwget\b.*\|.*\bsh\b",
    r"\bgit\s+push\s+--force\b",
    r"\bgit\s+reset\s+--hard\b",
])
```

### MaxFileSizeRule

Blocks write-category tool calls where the content exceeds a byte threshold.

**Default:** 1,000,000 bytes (1 MB).

This prevents the agent from writing extremely large files that might be generated content (base64-encoded binaries, dumped databases, etc.).

**Customization:**

```python
from devharness.policies.rules import MaxFileSizeRule

rule = MaxFileSizeRule(max_bytes=500_000)  # 500 KB
```

---

## Custom Policy Rules

Create rules that enforce your organization's specific constraints:

```python
from devharness.policies.rules import PolicyRule
from devharness.core.models import PolicyDecision, ToolCategory

class DenyProductionDatabaseRule(PolicyRule):
    name = "deny_production_db"

    def evaluate(self, tool_name, arguments, category):
        if tool_name != "shell":
            return None

        command = arguments.get("command", "")
        if "production" in command and ("psql" in command or "mysql" in command):
            return PolicyDecision(
                allowed=False,
                mode=ApprovalMode.AUTO_APPROVE_SAFE,
                reason="Direct production database access is denied.",
            )
        return None  # abstain
```

Register with the policy engine:

```python
engine = PolicyEngine(extra_rules=[DenyProductionDatabaseRule()])
```

---

## Policy Evaluation Order

1. **Denied tools list**: If the tool name is in `ThreadConfig.denied_tools`, deny immediately.
2. **Allowed tools list**: If `ThreadConfig.allowed_tools` is set and the tool is not in it, deny.
3. **Mode evaluation**: Apply the thread's `ApprovalMode` to determine baseline (allow, require approval, or deny).
4. **Custom rules**: If mode allows, run all `PolicyRule` instances. First deny wins.

At each stage, a deny is final. Subsequent stages cannot override a deny from an earlier stage.

---

## Allowed and Denied Tool Lists

Per-thread tool filtering, independent of approval mode:

```python
config = ThreadConfig(
    # Only these tools are available
    allowed_tools=["file_read", "file_write", "search"],

    # These tools are blocked even if in allowed_tools
    denied_tools=["shell"],
)
```

- `allowed_tools=None` means all registered tools are available.
- `denied_tools` takes precedence over `allowed_tools`.

---

## Approval Resolution

When a tool call requires approval, the thread pauses and an `ApprovalRequest` is created.

### Resolution Channels

**CLI:**

```bash
harness approve <thread_id> <approval_id> --approve
harness approve <thread_id> <approval_id> --deny --reason "Too dangerous"
```

**Web UI:** Interactive approve/deny buttons with optional reason field.

**Slack:** Block Kit messages with approve/deny action buttons. Responses are delivered via Socket Mode.

### ApprovalRequest Fields

| Field | Description |
|-------|-------------|
| `id` | Unique request identifier |
| `tool_call_id` | The tool call being gated |
| `tool_name` | Name of the tool |
| `arguments` | Arguments the tool would be called with |
| `category` | read, write, or execute |
| `reason` | Why approval is needed |
| `status` | pending, auto_approved, user_approved, denied |
| `decided_by` | "policy:<mode>", "user", or "slack" |
| `decided_at` | When the decision was made |
| `denial_reason` | Reason for denial (if denied) |

---

## Enforcement Rules

Enforcement rules are a separate system from policy rules. They run mechanical checks (linters, type checkers) against the codebase and inject correction prompts when violations are detected.

```python
from devharness.core.models import EnforcementRule

rule = EnforcementRule(
    name="no_any_types",
    check_command="mypy --strict src/ 2>&1 | grep 'Any'",
    error_pattern=r"error:.*Any",
    correction_prompt=(
        "Type checking found untyped code. Replace 'Any' with "
        "specific types. Check the mypy output for exact locations."
    ),
    architectural_layer="Types",
    enabled=True,
)
```

When an enforcement rule fails, `correction_prompt` is injected into the agent's context so it knows how to fix the violation.

---

## Recommended Configurations

### Solo Developer, Trusted Branch

```python
ThreadConfig(
    approval_mode=ApprovalMode.FULL_TRUST,
    verification_enabled=True,
)
```

Fast iteration. Trust the agent, but verify with tests and linting.

### Team Environment

```python
ThreadConfig(
    approval_mode=ApprovalMode.WORKSPACE_WRITE,
    denied_tools=["shell"],
)
```

Let the agent write code, but deny shell access entirely.

### Production Debugging

```python
ThreadConfig(
    approval_mode=ApprovalMode.READ_ONLY,
)
```

Agent investigates, human acts.

### Compliance-Sensitive

```python
ThreadConfig(
    approval_mode=ApprovalMode.APPROVAL_REQUIRED,
)
```

Full audit trail. Every action approved by a human.
